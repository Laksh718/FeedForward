"""Conditional WGAN-GP in plain PyTorch (CPU).

Generator: random noise plus the conditions (event, dish category, slot ...) -> a scaled log demand.
Critic: a scaled log demand plus the same conditions -> one score (higher means "looks real"). No sigmoid.
Wasserstein loss: the critic tries to score real above fake, the generator tries to raise the fake score.
Gradient penalty: keeps the critic smooth, so training stays stable (lambda 10).
"""

import torch
from torch import nn

NOISE_DIM = 32
HIDDEN = 128
GP_LAMBDA = 10.0
CRITIC_STEPS = 5     # critic updates per generator update
LR, BETAS = 1e-4, (0.5, 0.9)


def mlp(n_in: int, n_out: int, hidden: int = HIDDEN, layers: int = 3) -> nn.Sequential:
    """Small network: `layers` hidden layers of LeakyReLU, then a linear output."""
    blocks, size = [], n_in
    for _ in range(layers):
        blocks += [nn.Linear(size, hidden), nn.LeakyReLU(0.2)]
        size = hidden
    return nn.Sequential(*blocks, nn.Linear(size, n_out))


class Generator(nn.Module):
    """noise + conditions -> scaled log demand."""

    def __init__(self, n_cond: int) -> None:
        super().__init__()
        self.net = mlp(NOISE_DIM + n_cond, 1)

    def forward(self, noise: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([noise, cond], dim=1))


class Critic(nn.Module):
    """scaled log demand + conditions -> score."""

    def __init__(self, n_cond: int) -> None:
        super().__init__()
        self.net = mlp(1 + n_cond, 1)

    def forward(self, y: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([y, cond], dim=1))


def gradient_penalty(critic: Critic, real: torch.Tensor, fake: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
    """Penalty (norm of the critic gradient minus 1) squared, at random points between real and fake."""
    mix = torch.rand(len(real), 1)
    point = (mix * real + (1 - mix) * fake).requires_grad_(True)
    score = critic(point, cond)
    grad = torch.autograd.grad(score.sum(), point, create_graph=True)[0]
    return ((grad.norm(2, dim=1) - 1) ** 2).mean()


def critic_loss(critic: Critic, real: torch.Tensor, fake: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
    """Wasserstein loss for the critic (fake score minus real score) plus the gradient penalty."""
    return critic(fake, cond).mean() - critic(real, cond).mean() + GP_LAMBDA * gradient_penalty(critic, real, fake, cond)


def generator_loss(critic: Critic, fake: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
    """Wasserstein loss for the generator: make fake rows score high."""
    return -critic(fake, cond).mean()


@torch.no_grad()
def sample(generator: Generator, cond: torch.Tensor, seed: int) -> torch.Tensor:
    """One scaled log demand per condition row, with its own fixed noise stream."""
    gen = torch.Generator().manual_seed(seed)
    noise = torch.randn(len(cond), NOISE_DIM, generator=gen)
    generator.eval()
    return generator(noise, cond).squeeze(1)
