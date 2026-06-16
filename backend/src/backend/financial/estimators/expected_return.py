"""Expected-return estimator μ.

μ is the per-asset mean of *real* hourly returns over the trailing τ-window.
Returns may carry NaN gaps — closed hours and not-yet-listed history are missing,
never fabricated — so the mean ignores NaNs. An asset with fewer than
``config.MIN_RETURN_OBS`` real observations gets μ = 0: it's held for
diversification rather than chased on a mean estimated from a handful of points.
"""

from __future__ import annotations

import numpy as np

from ... import config


def expected_return(returns: np.ndarray, tau_hours: int, min_obs: int | None = None) -> np.ndarray:
    """Expected returns μ (N,) over the last ``tau_hours`` of real hourly returns.

    Args:
        returns: shape (T, N) — T hourly observations across N assets, NaN where
            an asset had no data that hour.
        tau_hours: lookback length. If τ ≥ T, the full history is used.
        min_obs: assets with fewer real observations get μ = 0
            (defaults to ``config.MIN_RETURN_OBS``).

    Returns:
        μ (N,), the NaN-aware column mean over the τ-window.
    """
    if returns.ndim != 2:
        raise ValueError(f"returns must be 2-D (T, N), got shape {returns.shape}")
    if tau_hours <= 0:
        raise ValueError(f"tau_hours must be positive, got {tau_hours}")
    min_obs = config.MIN_RETURN_OBS if min_obs is None else min_obs

    window = returns[-tau_hours:]
    counts = np.isfinite(window).sum(axis=0)
    sums = np.nansum(window, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = np.where(counts > 0, sums / counts, 0.0)
    return np.where(counts >= min_obs, means, 0.0)
