"""SliderValues (0–100) → SliderParams (γ, w_max, w_min, rebalance cadence).

SINGLE SOURCE OF TRUTH for the slider → physical-parameter mapping.
Frontend never sees physical params; it only sends 0–100 sliders.

The three sliders (mirrors mvp/src/api/types.ts and mvp/src/utils/strategy.ts):
- Risk Preference 100    → aggressive/speculative → low γ (inverted, log-scaled)
- Max Position Size 100  → heavy concentration → high w_max (relative to basket)
- Rebalance Frequency 100→ hourly scheduled re-optimization (hard cap)

The dropped sliders' roles moved elsewhere: diversification → the player's
basket selection; holding style → fixed lookbacks in config. There is no
turnover term — a retune liquidates and reallocates from scratch.
"""

from __future__ import annotations

import math

from .. import config
from ..api.schemas import SliderValues
from .qubo_encoder import units_for_cardinality
from .types import SliderParams


def _lerp(t: float, lo: float, hi: float) -> float:
    """Linear interpolation. t in [0, 1]."""
    return lo + (hi - lo) * t


def _log_lerp(t: float, lo: float, hi: float) -> float:
    """Log-scaled interpolation. t in [0, 1]."""
    return math.exp(_lerp(t, math.log(lo), math.log(hi)))


def max_position_cap(basket_size: int, value: float) -> float:
    """Per-asset cap as a fraction, RELATIVE to the basket.

    Mirrors mvp/src/utils/strategy.ts::maxPositionCapPct: an absolute cap below
    1/n is infeasible, and with a big basket a large absolute cap never binds.
    Sweeps from equal weight (1/n) up to W_MAX_CEILING; a 1-asset basket is
    always 100%.
    """
    n = max(1, basket_size)
    floor = 1.0 / n
    ceiling = max(config.W_MAX_CEILING, floor)
    return floor + (value / 100.0) * (ceiling - floor)


def rebalance_every_hours(value: float) -> int:
    """Rebalance slider → scheduled cadence in hours (tiers, hourly hard cap).

    Mirrors mvp/src/utils/strategy.ts::rebalanceEveryHours.
    """
    tiers = config.REBALANCE_TIERS_HOURS
    index = min(len(tiers) - 1, int(value // 20))
    return tiers[index]


def map_sliders(sliders: SliderValues, basket_size: int) -> SliderParams:
    """Map slider values to physical optimization parameters.

    `basket_size` is the number of assets the player selected — w_max, w_min, and
    the cardinality K are defined relative to it. The active route is
    config.OPTIMIZATION_MODE ("method3" default, "convex" fallback).
    """

    # Risk Preference: high slider → aggressive → low γ (inverted, log-scaled)
    risk_t = 1.0 - sliders.risk_preference / 100.0
    gamma = _log_lerp(risk_t, *config.GAMMA_RANGE)

    # Rebalance Frequency: scheduled re-optimization cadence
    rebalance_hours = rebalance_every_hours(sliders.rebalance_frequency)

    if config.OPTIMIZATION_MODE == "method3":
        u_min = config.METHOD3_U_MIN
        # K (count) from the dedicated slider. Floor 3 (K=2 on the integer grid forces a
        # degenerate 50/50 split), capped to the basket and the grid's unit ceiling.
        k = sliders.hold_count if sliders.hold_count is not None else basket_size
        k = max(3, min(int(k), basket_size, config.METHOD3_MAX_UNITS))
        # Grid M is the smallest power of two that fits K (fewest QUBO vars → best QPU
        # feasibility); units_for_cardinality guarantees M ≥ K so the budget is placeable.
        m_units = units_for_cardinality(k)
        w_min = u_min / m_units  # integer-grid floor = the minimum buy-in if held
        # K-dominant, grid-aware: the cap can't make the INTEGER budget unreachable.
        # K held assets must place M units, so each may need up to ⌈M/K⌉ units;
        # floor(w_max·M) ≥ ⌈M/K⌉ requires w_max ≥ ⌈M/K⌉/M (stricter than 1/K).
        grid_min_cap = math.ceil(m_units / k) / m_units
        w_max = max(max_position_cap(basket_size, sliders.max_position_size), grid_min_cap)
        return SliderParams(
            gamma=gamma,
            w_max=w_max,
            w_min=w_min,
            rebalance_hours=rebalance_hours,
            cardinality_k=k,
            n_units_M=m_units,
            u_min_units=u_min,
        )

    # Convex fallback: every selected asset is held (no cardinality).
    w_max = max_position_cap(basket_size, sliders.max_position_size)
    w_min = config.MIN_POSITION_FRACTION / max(1, basket_size)
    return SliderParams(
        gamma=gamma,
        w_max=w_max,
        w_min=w_min,
        rebalance_hours=rebalance_hours,
    )
