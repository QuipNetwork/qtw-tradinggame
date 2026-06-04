"""SliderValues (0–100) → SliderParams (γ, w_max, τ, K, λ_t).

SINGLE SOURCE OF TRUTH for the slider → physical-parameter mapping.
Frontend never sees physical params; it only sends 0–100 sliders.

UI convention: slider at 100 = max of the conceptual axis.
- Risk Preference 100   → aggressive → low γ
- Trade Size 100        → high concentration → high w_max
- Holding Style 100     → patient → long τ
- Diversification 100   → high diversification → high K
- Trading Activity 100  → high activity → low λ_t (free to move)
"""

from __future__ import annotations

import math

from .. import config
from ..api.schemas import SliderValues
from .types import SliderParams


def _lerp(t: float, lo: float, hi: float) -> float:
    """Linear interpolation. t in [0, 1]."""
    return lo + (hi - lo) * t


def _log_lerp(t: float, lo: float, hi: float) -> float:
    """Log-scaled interpolation. t in [0, 1]."""
    return math.exp(_lerp(t, math.log(lo), math.log(hi)))


def map_sliders(sliders: SliderValues) -> SliderParams:
    """Map 0–100 slider values to physical optimization parameters."""

    # Risk Preference: high slider → aggressive → low γ
    # Invert: t=1 means risk_preference=100 means low γ
    risk_t = 1.0 - sliders.risk_preference / 100.0
    gamma = _log_lerp(risk_t, *config.GAMMA_RANGE)

    # Diversification: high slider → high K (linear, integer). Computed before
    # w_max because w_max's floor depends on K.
    div_t = sliders.diversification / 100.0
    K_lo, K_hi = config.K_RANGE
    K = K_lo + round((K_hi - K_lo) * div_t)

    # Trade Size: per-asset cap from equal-weight (1/K) to concentrated (W_MAX_HI).
    # Flooring at 1/K guarantees K·w_max ≥ 1 (budget always reachable); at the low
    # end w_max = 1/K forces exactly-K equal weights.
    trade_t = sliders.trade_size / 100.0
    w_max = _lerp(trade_t, 1.0 / K, config.W_MAX_HI)

    # Minimum size of a selected position → makes the cardinality exactly-K.
    w_min = config.MIN_POSITION_FRACTION / K

    # Holding Style: high slider → patient → long τ (log-scaled)
    hold_t = sliders.holding_style / 100.0
    tau_hours = int(round(_log_lerp(hold_t, *config.TAU_RANGE_HOURS)))

    # Trading Activity: high slider → free to move → low λ_t
    # Invert: t=1 means trading_activity=100 means low λ_t
    if config.V0_LAMBDA_T_FORCED_ZERO:
        lambda_t = 0.0
    else:
        activity_t = 1.0 - sliders.trading_activity / 100.0
        lambda_t = _lerp(activity_t, 0.0, config.LAMBDA_T_MAX)

    return SliderParams(
        gamma=gamma,
        w_max=w_max,
        w_min=w_min,
        tau_hours=tau_hours,
        K=K,
        lambda_t=lambda_t,
    )
