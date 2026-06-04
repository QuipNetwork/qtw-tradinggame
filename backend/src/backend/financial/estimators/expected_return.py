"""Expected-return estimator μ.

μ is the per-asset mean of hourly returns over the user's τ-window. τ is the
only quantity a slider feeds into the *input data* (Holding Style → τ): a patient
agent averages over a long lookback, a restless one over a short, recent window.
This module is pure; A later pass wires the returns source (prices/history.py).
"""

from __future__ import annotations

import numpy as np


def expected_return(returns: np.ndarray, tau_hours: int) -> np.ndarray:
    """Expected returns μ (N,) over the last ``tau_hours`` of hourly returns.

    Args:
        returns: shape (T, N) — T hourly observations across N assets.
        tau_hours: lookback length. If τ ≥ T, the full history is used.

    Returns:
        μ (N,), the column-wise mean over the τ-window.
    """
    if returns.ndim != 2:
        raise ValueError(f"returns must be 2-D (T, N), got shape {returns.shape}")
    if tau_hours <= 0:
        raise ValueError(f"tau_hours must be positive, got {tau_hours}")
    window = returns[-tau_hours:]
    return window.mean(axis=0)
