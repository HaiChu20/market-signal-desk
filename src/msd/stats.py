"""Sharpe-ratio inference with non-normality and multiple-trial correction."""
from __future__ import annotations

from math import erf, exp, sqrt
from statistics import NormalDist

import numpy as np

EULER_GAMMA = 0.5772156649015329


def sharpe_moments(returns: np.ndarray) -> tuple[float, float, float, int]:
    x = np.asarray(returns, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return float("nan"), float("nan"), float("nan"), len(x)
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    if sd == 0:
        return float("nan"), 0.0, 3.0, len(x)
    centered = x - mean
    m2 = float(np.mean(centered ** 2))
    skew = float(np.mean(centered ** 3) / m2 ** 1.5)
    kurtosis = float(np.mean(centered ** 4) / m2 ** 2)  # Pearson, not excess
    return mean / sd, skew, kurtosis, len(x)


def probabilistic_sharpe_ratio(sharpe: float, n: int, skew: float, kurtosis: float,
                               benchmark: float = 0.0) -> float:
    """PSR with sample skew and Pearson kurtosis, using Bailey–López de Prado."""
    if n < 2 or not np.isfinite(sharpe):
        return float("nan")
    variance = (1 - skew * sharpe + ((kurtosis - 1) / 4) * sharpe ** 2) / (n - 1)
    if variance <= 0:
        return float("nan")
    z = (sharpe - benchmark) / sqrt(variance)
    return 0.5 * (1 + erf(z / sqrt(2)))


def expected_max_sharpe(trial_sharpes: np.ndarray, n_trials: float) -> float:
    """Null benchmark SR0 from Bailey–López de Prado (2014).

    ``trial_sharpes`` supplies the variance of estimated trial Sharpes. Under
    the null every true Sharpe is zero, so there is no mean term.
    """
    values = np.asarray(trial_sharpes, dtype=float)
    values = values[np.isfinite(values)]
    if n_trials <= 1:
        return 0.0
    if len(values) < 2:
        return float("nan")
    variance = float(values.var(ddof=1))
    if variance <= 0:
        return 0.0
    p1 = min(1 - 1 / n_trials, 1 - 1e-12)
    p2 = min(1 - 1 / (n_trials * exp(1)), 1 - 1e-12)
    a = NormalDist().inv_cdf(p1)
    b = NormalDist().inv_cdf(p2)
    return sqrt(variance) * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe_ratio(returns: np.ndarray, trial_sharpes: np.ndarray,
                          n_trials: float) -> tuple[float, float, float]:
    sr, skew, kurtosis, n = sharpe_moments(returns)
    benchmark = expected_max_sharpe(trial_sharpes, n_trials)
    return probabilistic_sharpe_ratio(sr, n, skew, kurtosis, benchmark), sr, benchmark
