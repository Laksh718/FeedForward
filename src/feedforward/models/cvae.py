"""Conditional variational autoencoder (CVAE) for demand. Plain PyTorch, CPU.

Idea in plain words
-------------------
We want p(demand | conditions), a whole distribution, not one number. A VAE learns this by:
  encoder  q(z | y, c): looks at the true (log) demand y and the conditions c and says "this day looks like
           a point z in a small hidden space". It outputs a mean and a log variance, not one point.
  sampling z = mean + std * noise  (the reparameterisation trick: randomness is moved outside the network,
           so gradients can flow back through mean and std).
  decoder  p(y | z, c): turns z and the conditions back into a demand, again as a mean and a log variance.
  loss     = reconstruction (Gaussian negative log likelihood, which generalises MSE because it also learns
           the variance) + beta * KL (keeps q(z | y, c) close to the standard normal prior N(0, I)).
At forecast time the conditions c are fixed (date, dish, weather ...), z is drawn from N(0, I) many times and
decoded. The spread of those samples is the forecast range (P10, P50, P90). This is why a generative model
gives a range while a plain regressor gives one number.

Hand engineered versus learned: calendar, weather and lag features are hand engineered inputs. The dish
embedding (a table of 8 numbers per dish) is LEARNED by the network from data. The optional GRU summarises the
21 day history on its own (--encoder gru) instead of relying only on the hand made lag features.
"""

import random
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

from feedforward import config as C

LOGVAR_MIN, LOGVAR_MAX = -8.0, 4.0  # keeps the variances numerically safe


def set_seed(seed: int = C.SEED) -> None:
    """Fix python, numpy and torch randomness. Call it BEFORE the model is built (its starting weights are random)."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


@dataclass
class CVAEConfig:
    """All settings of the model and training in one place (defaults live in config.py)."""

    latent_dim: int = C.VAE_LATENT
    hidden: int = C.VAE_HIDDEN
    emb_dim: int = C.VAE_EMB
    dropout: float = C.VAE_DROPOUT
    lr: float = C.VAE_LR
    weight_decay: float = C.VAE_WEIGHT_DECAY
    batch_size: int = C.VAE_BATCH
    max_epochs: int = C.VAE_EPOCHS
    anneal_epochs: int = C.VAE_ANNEAL_EPOCHS
    patience: int = C.VAE_PATIENCE
    encoder: str = "mlp"  # "mlp" or "gru"
    gru_hidden: int = 32
    free_bits: float = C.VAE_FREE_BITS


class CVAE(nn.Module):
    """Conditional VAE: encoder q(z|y,c), decoder p(y|z,c) and a condition builder."""

    def __init__(self, n_dishes: int, n_num: int, cfg: CVAEConfig, n_seq_channels: int = 5) -> None:
        super().__init__()
        self.cfg = cfg
        self.dish_emb = nn.Embedding(n_dishes, cfg.emb_dim)  # learned representation of each dish
        self.gru = nn.GRU(n_seq_channels, cfg.gru_hidden, batch_first=True) if cfg.encoder == "gru" else None
        c_dim = cfg.emb_dim + n_num + (cfg.gru_hidden if self.gru else 0)
        h, act = cfg.hidden, nn.LeakyReLU(0.1)  # LeakyReLU: like ReLU but never fully "dead"
        self.enc = nn.Sequential(nn.Linear(1 + c_dim, h), act, nn.Dropout(cfg.dropout), nn.Linear(h, h), act)
        self.enc_mu, self.enc_logvar = nn.Linear(h, cfg.latent_dim), nn.Linear(h, cfg.latent_dim)
        self.dec = nn.Sequential(nn.Linear(cfg.latent_dim + c_dim, h), act, nn.Dropout(cfg.dropout),
                                 nn.Linear(h, h), act)
        self.dec_mean, self.dec_logvar = nn.Linear(h, 1), nn.Linear(h, 1)

    def condition(self, dish_idx: torch.Tensor, x_num: torch.Tensor, x_seq: torch.Tensor | None = None):
        """Build c = [learned dish embedding, scaled numeric features, optional GRU summary of history]."""
        parts = [self.dish_emb(dish_idx), x_num]
        if self.gru is not None:
            parts.append(self.gru(x_seq)[1][-1])  # last hidden state summarises the 21 days
        return torch.cat(parts, dim=1)

    def encode(self, y: torch.Tensor, c: torch.Tensor):
        """Mean and log variance of q(z | y, c)."""
        h = self.enc(torch.cat([y, c], dim=1))
        return self.enc_mu(h), self.enc_logvar(h).clamp(LOGVAR_MIN, LOGVAR_MAX)

    def decode(self, z: torch.Tensor, c: torch.Tensor):
        """Mean and log variance of p(y | z, c)."""
        h = self.dec(torch.cat([z, c], dim=1))
        return self.dec_mean(h), self.dec_logvar(h).clamp(LOGVAR_MIN, LOGVAR_MAX)

    def forward(self, y, dish_idx, x_num, x_seq=None, off=None):
        """Training pass: encode, sample z with the reparameterisation trick, decode.

        `off` is the log of expected attendance (scaled): demand grows with the number of people, so the
        network only has to learn the deviation from "demand follows attendance". It keeps predictions sane in
        situations the training data never combined (for example first years away while others are in class).
        """
        off = torch.zeros_like(y) if off is None else off
        c = self.condition(dish_idx, x_num, x_seq)
        mu, logvar = self.encode(y - off, c)
        z = mu + torch.exp(0.5 * logvar) * torch.randn_like(mu)
        mean, dec_logvar = self.decode(z, c)
        return mean + off, dec_logvar, mu, logvar


def vae_loss(y, mean, dec_logvar, mu, logvar, beta: float, weight: torch.Tensor | None = None,
             free_bits: float = 0.0):
    """Reconstruction (Gaussian NLL) + beta * KL.

    free_bits: each latent dimension may use up to this many nats of KL for free. It stops the encoder from
    switching the latent space off completely (posterior collapse). Returns total, reconstruction, KL and the
    KL of each latent dimension (the numbers to check for collapse).
    """
    w = torch.ones(len(y)) if weight is None else weight
    recon = 0.5 * (dec_logvar + (y - mean) ** 2 / torch.exp(dec_logvar)).squeeze(1)
    kl_dim = -0.5 * (1 + logvar - mu ** 2 - torch.exp(logvar))        # one number per sample and dimension
    kl_mean = (kl_dim * w[:, None]).sum(dim=0) / w.sum()               # average over the batch
    recon_mean = (recon * w).sum() / w.sum()
    total = recon_mean + beta * torch.clamp(kl_mean, min=free_bits).sum()
    return total, recon_mean, kl_mean.sum(), kl_mean


def beta_at(epoch: int, anneal_epochs: int) -> float:
    """KL annealing: beta rises linearly from 0 to 1 over the first epochs so the decoder learns first."""
    return min(1.0, epoch / max(1, anneal_epochs))


@torch.no_grad()
def evaluate_loss(model: CVAE, tensors: dict) -> dict:
    """Loss on a held out set with beta = 1 (the true VAE objective), dropout off, fixed noise."""
    model.eval()
    with torch.random.fork_rng():  # fixed noise for comparable curves, without disturbing training noise
        torch.manual_seed(C.SEED)
        out = model(tensors["y"], tensors["dish"], tensors["x"], tensors.get("seq"), tensors.get("off"))
    total, recon, kl, kl_dim = vae_loss(tensors["y"], *out, beta=1.0, free_bits=0.0)
    return {"loss": float(total), "recon": float(recon), "kl": float(kl), "kl_dim": kl_dim.numpy()}


def train_cvae(model: CVAE, make_train, val: dict | None, fixed_epochs: int | None = None,
               log: bool = True) -> tuple[CVAE, dict]:
    """Train with Adam, KL annealing and early stopping on validation loss.

    make_train(epoch) returns a dict of tensors (y, dish, x, optional seq and weight); it is a function so the
    caller can add fresh weather forecast noise each epoch. With fixed_epochs (final retrain, no validation
    set) it trains exactly that many epochs.
    """
    cfg = model.cfg  # the seed was set by the caller before the model was built (see set_seed)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    hist = {"train_loss": [], "val_loss": [], "train_recon": [], "train_kl": [], "val_kl": [], "beta": [],
            "val_kl_dim": []}
    best, best_state, best_epoch, bad = np.inf, None, 0, 0
    n_epochs = fixed_epochs or cfg.max_epochs
    for epoch in range(1, n_epochs + 1):
        model.train()
        data, beta = make_train(epoch), beta_at(epoch, cfg.anneal_epochs)
        order = torch.randperm(len(data["y"]))
        sums = np.zeros(3)
        for i in range(0, len(order), cfg.batch_size):
            idx = order[i:i + cfg.batch_size]
            seq = data["seq"][idx] if "seq" in data else None
            off = data["off"][idx] if "off" in data else None
            mean, dec_lv, mu, lv = model(data["y"][idx], data["dish"][idx], data["x"][idx], seq, off)
            total, recon, kl, _ = vae_loss(data["y"][idx], mean, dec_lv, mu, lv, beta,
                                           data["weight"][idx] if "weight" in data else None, cfg.free_bits)
            opt.zero_grad()
            total.backward()  # backpropagation: gradients of the loss for every weight
            opt.step()        # gradient descent step (Adam)
            sums += np.array([total.item(), recon.item(), kl.item()]) * len(idx)
        sums /= len(order)
        hist["train_loss"].append(sums[0])
        hist["train_recon"].append(sums[1])
        hist["train_kl"].append(sums[2])
        hist["beta"].append(beta)
        if val is not None:
            v = evaluate_loss(model, val)
            hist["val_loss"].append(v["loss"])
            hist["val_kl"].append(v["kl"])
            hist["val_kl_dim"].append(v["kl_dim"])
            if beta >= 1.0:  # only judge overfitting once the loss is the real objective
                if v["loss"] < best - 1e-4:
                    best, bad, best_epoch = v["loss"], 0, epoch
                    best_state = {k: t.clone() for k, t in model.state_dict().items()}
                else:
                    bad += 1
                    if bad >= cfg.patience:
                        break
            if log and epoch % 10 == 0:
                print(f"epoch {epoch:3d} beta {beta:.2f} train {sums[0]:.3f} val {v['loss']:.3f} kl {v['kl']:.2f}")
    if best_state is not None:
        model.load_state_dict(best_state)
    hist["best_epoch"] = best_epoch or n_epochs
    return model, hist


@torch.no_grad()
def sample_log_quantiles(model: CVAE, dish_idx, x_num, x_seq, off, y_mean: float, y_std: float, quantiles,
                         n_samples: int = C.N_SAMPLES, seed: int = C.SEED, chunk: int = 256) -> dict:
    """Draw z from N(0, I) n_samples times per row, decode, and return quantiles of log1p(demand).

    Conditions c are fixed per row. Each decoded sample also gets the decoder's own noise, so the samples are
    plausible outcomes, not just plausible means.
    """
    model.eval()
    gen = torch.Generator().manual_seed(seed)
    outs = {q: [] for q in quantiles}
    for i in range(0, len(dish_idx), chunk):
        sl = slice(i, i + chunk)
        c = model.condition(dish_idx[sl], x_num[sl], x_seq[sl] if x_seq is not None else None)
        n = len(c)
        o = off[sl].repeat_interleave(n_samples, dim=0)
        c_rep = c.repeat_interleave(n_samples, dim=0)
        z = torch.randn(n * n_samples, model.cfg.latent_dim, generator=gen)
        mean, logvar = model.decode(z, c_rep)
        y = mean + o + torch.exp(0.5 * logvar) * torch.randn(mean.shape, generator=gen)
        y = (y.view(n, n_samples) * y_std + y_mean)
        for q in quantiles:
            outs[q].append(torch.quantile(y, q, dim=1).numpy())
    return {q: np.concatenate(v) for q, v in outs.items()}
