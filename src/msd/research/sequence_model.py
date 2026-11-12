"""Compact multi-timeframe CNN and geometric-baseline residual barrier head."""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from msd.research.sequence_data import WINDOWS


class SequenceModel(nn.Module):
    def __init__(self, dense_dim: int, channels: int = 6, width: int = 24,
                 sides: int = 2, sl_count: int = 5, tp_count: int = 7):
        super().__init__()
        self.grid_shape = (sides, sl_count, tp_count)
        self.encoders = nn.ModuleDict({tf: nn.Sequential(
            nn.Conv1d(channels, width, 5, padding=2), nn.GELU(),
            nn.Conv1d(width, width, 5, padding=2), nn.GELU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten()) for tf in WINDOWS})
        self.head = nn.Sequential(nn.Linear(width * 4 + dense_dim, width * 4),
                                  nn.GELU(), nn.Linear(width * 4, sides * sl_count * tp_count))
        # Start exactly at the geometric baseline, allowing the model to learn a residual.
        nn.init.zeros_(self.head[-1].weight)
        nn.init.zeros_(self.head[-1].bias)

    def forward(self, windows: dict[str, torch.Tensor], dense: torch.Tensor,
                p0: torch.Tensor) -> torch.Tensor:
        encoded = [self.encoders[tf](windows[tf].transpose(1, 2)) for tf in WINDOWS]
        offset = self.head(torch.cat([*encoded, dense], dim=1)).reshape(-1, *self.grid_shape)
        return torch.logit(p0.clamp(1e-6, 1 - 1e-6)) + offset


def monotonicity_penalty(logits: torch.Tensor) -> torch.Tensor:
    """Penalize TP probabilities rising with TP or falling with SL distance."""
    p = logits.sigmoid()
    return F.relu(p[..., 1:] - p[..., :-1]).square().mean() + \
        F.relu(p[:, :, :-1, :] - p[:, :, 1:, :]).square().mean()


def barrier_loss(logits: torch.Tensor, target: torch.Tensor, mask: torch.Tensor,
                 monotonic_weight: float = 1.) -> torch.Tensor:
    if not mask.any():
        raise ValueError("Batch has no resolved barrier outcomes")
    raw = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    return raw[mask].mean() + monotonic_weight * monotonicity_penalty(logits)
