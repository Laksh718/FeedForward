"""Train the rare event GAN.

python -m feedforward.models.train_gan --epochs 600 --seed 42 --out artifacts/gan

Every 50 epochs it checks for mode collapse (does the generator still spread its outputs for each event type?)
and for how close generated demand is to real demand (Kolmogorov-Smirnov distance). The best checkpoint is kept.
Training stops early if the generator spread is almost zero.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from scipy.stats import ks_2samp

from feedforward import config as C
from feedforward.data.gan_data import EVENT_TYPES, GAN_DIR, GanScaler, build_table
from feedforward.models.gan import BETAS, CRITIC_STEPS, LR, NOISE_DIM, Critic, Generator, critic_loss, generator_loss, sample

BATCH = 128
CHECK_EVERY = 50
COLLAPSE_RATIO = 0.1     # generated spread below 10 percent of the real spread counts as collapse


def collapse_check(generator: Generator, cond: torch.Tensor, y: np.ndarray, events: np.ndarray, seed: int) -> dict:
    """Per event type: std of generated and real outputs, and the KS distance between them."""
    fake = sample(generator, cond, seed).numpy()
    generator.train()
    out = {}
    for name in EVENT_TYPES:
        m = events == name
        if m.sum() < 5:
            continue
        out[name] = {"fake_std": float(fake[m].std()), "real_std": float(y[m].std()),
                     "ks": float(ks_2samp(fake[m], y[m]).statistic)}
    return out


def train(cond: np.ndarray, y: np.ndarray, events: np.ndarray, epochs: int, seed: int, log: bool = True,
          check_every: int = CHECK_EVERY) -> tuple[Generator, dict]:
    """Train the WGAN-GP. The seed is set before any network is built. Returns the best generator and a summary."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    n_cond = cond.shape[1]
    gen, critic = Generator(n_cond), Critic(n_cond)
    opt_g = torch.optim.Adam(gen.parameters(), lr=LR, betas=BETAS)
    opt_c = torch.optim.Adam(critic.parameters(), lr=LR, betas=BETAS)
    cond_t, y_t = torch.from_numpy(cond), torch.from_numpy(y.reshape(-1, 1))
    n = len(cond_t)
    steps = max(1, n // BATCH)
    best, best_epoch, best_state, hist, checks, step, stopped = np.inf, 0, None, [], [], 0, ""
    for epoch in range(1, epochs + 1):
        order = torch.randperm(n)
        c_sum, g_sum, g_n = 0.0, 0.0, 0
        for i in range(steps):
            idx = order[i * BATCH:(i + 1) * BATCH]
            real, c = y_t[idx], cond_t[idx]
            with torch.no_grad():
                fake = gen(torch.randn(len(idx), NOISE_DIM), c)
            loss_c = critic_loss(critic, real, fake, c)
            opt_c.zero_grad()
            loss_c.backward()
            opt_c.step()
            c_sum += loss_c.item()
            step += 1
            if step % CRITIC_STEPS == 0:
                loss_g = generator_loss(critic, gen(torch.randn(len(idx), NOISE_DIM), c), c)
                opt_g.zero_grad()
                loss_g.backward()
                opt_g.step()
                g_sum += loss_g.item()
                g_n += 1
        hist.append({"epoch": epoch, "critic_loss": c_sum / steps, "generator_loss": g_sum / max(g_n, 1)})
        if epoch % check_every == 0 or epoch == epochs:
            res = collapse_check(gen, cond_t, y, events, seed)
            mean_ks = float(np.mean([v["ks"] for v in res.values()]))
            collapsed = all(v["fake_std"] < COLLAPSE_RATIO * v["real_std"] for v in res.values())
            checks.append({"epoch": epoch, "mean_ks": mean_ks, "by_event": res, "collapsed": collapsed})
            if log:
                print(f"epoch {epoch:4d} critic {hist[-1]['critic_loss']:.3f} generator {hist[-1]['generator_loss']:.3f} "
                      f"mean KS {mean_ks:.3f} collapsed {collapsed}")
            if mean_ks < best and not collapsed:
                best, best_epoch = mean_ks, epoch
                best_state = {k: v.clone() for k, v in gen.state_dict().items()}
            if collapsed:
                stopped = f"mode collapse at epoch {epoch}"
                break
    if best_state is None:                       # never had a good check: keep the last generator
        best_state, best_epoch = gen.state_dict(), len(hist)
    gen.load_state_dict(best_state)
    summary = {"epochs_requested": epochs, "epochs_trained": len(hist), "best_epoch": best_epoch,
               "best_mean_ks": None if best_epoch == 0 or best == np.inf else best, "stopped_early": stopped, "seed": seed,
               "rows": int(n), "n_conditions": int(n_cond), "checks": checks,
               "last_critic_loss": hist[-1]["critic_loss"], "last_generator_loss": hist[-1]["generator_loss"]}
    return gen, summary | {"history": hist}


def main() -> None:
    """Command line entry point."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=600)
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--out", default=str(GAN_DIR))
    args = ap.parse_args()
    out = Path(args.out)
    table, data_log = build_table(args.seed)
    scaler = GanScaler().fit(table)
    cond, y = scaler.conditions(table), scaler.scale_target(table["demand_qty"]).ravel()
    t0 = time.time()
    gen, summary = train(cond, y, table["event_type"].to_numpy(), args.epochs, args.seed)
    out.mkdir(parents=True, exist_ok=True)
    scaler.save(out)
    torch.save({"state": gen.state_dict(), "n_cond": cond.shape[1]}, out / "generator.pt")
    history = summary.pop("history")
    summary |= {"seconds": round(time.time() - t0), "data": data_log}
    (out / "training_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out / "training_history.json").write_text(json.dumps(history), encoding="utf-8")
    print(f"saved generator, scaler and summary to {out} (best epoch {summary['best_epoch']}, {summary['seconds']} s)")


if __name__ == "__main__":
    main()
