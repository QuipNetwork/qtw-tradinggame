"""slider_map: range coverage, the two inversions, and the V0 λ_t=0 clamp."""

from __future__ import annotations

import pytest

from backend import config
from backend.api.schemas import SliderValues
from backend.financial.slider_map import map_sliders


def _sliders(**overrides: float) -> SliderValues:
    base = {
        "tradingActivity": 50,
        "riskPreference": 50,
        "tradeSize": 50,
        "holdingStyle": 50,
        "diversification": 50,
    }
    base.update(overrides)
    return SliderValues(**base)


def test_risk_preference_is_inverted():
    """Slider at 100 = aggressive = low γ; at 0 = conservative = high γ."""
    aggressive = map_sliders(_sliders(riskPreference=100))
    conservative = map_sliders(_sliders(riskPreference=0))
    gamma_lo, gamma_hi = config.GAMMA_RANGE
    assert aggressive.gamma == pytest.approx(gamma_lo, rel=1e-6)
    assert conservative.gamma == pytest.approx(gamma_hi, rel=1e-6)
    assert aggressive.gamma < conservative.gamma


def test_trade_size_spans_equal_weight_to_concentrated():
    low = map_sliders(_sliders(tradeSize=0))
    high = map_sliders(_sliders(tradeSize=100))
    # Floor is equal weight (1/K); ceiling is the global concentration cap.
    assert low.w_max == pytest.approx(1.0 / low.K)
    assert high.w_max == pytest.approx(config.W_MAX_HI)
    assert low.w_max < high.w_max


def test_min_position_makes_exactly_k_feasible():
    for div in (0, 50, 100):
        params = map_sliders(_sliders(diversification=div))
        assert params.w_min == pytest.approx(config.MIN_POSITION_FRACTION / params.K)
        assert params.w_min <= params.w_max
        assert params.K * params.w_min <= 1.0  # budget reachable with K positions


def test_holding_style_spans_tau_range():
    restless = map_sliders(_sliders(holdingStyle=0))
    patient = map_sliders(_sliders(holdingStyle=100))
    tau_lo, tau_hi = config.TAU_RANGE_HOURS
    assert restless.tau_hours == tau_lo
    assert patient.tau_hours == tau_hi
    assert restless.tau_hours < patient.tau_hours


def test_diversification_spans_K_range_as_int():
    k_lo, k_hi = config.K_RANGE
    assert map_sliders(_sliders(diversification=0)).K == k_lo
    assert map_sliders(_sliders(diversification=100)).K == k_hi
    mid = map_sliders(_sliders(diversification=50)).K
    assert isinstance(mid, int)
    assert k_lo <= mid <= k_hi


def test_trading_activity_forced_zero_in_v0():
    assert config.V0_LAMBDA_T_FORCED_ZERO is True
    for value in (0, 25, 50, 75, 100):
        assert map_sliders(_sliders(tradingActivity=value)).lambda_t == 0.0


def test_every_param_stays_in_bounds_across_the_grid():
    for value in range(0, 101, 5):
        params = map_sliders(
            _sliders(
                tradingActivity=value,
                riskPreference=value,
                tradeSize=value,
                holdingStyle=value,
                diversification=value,
            )
        )
        gamma_lo, gamma_hi = config.GAMMA_RANGE
        tau_lo, tau_hi = config.TAU_RANGE_HOURS
        k_lo, k_hi = config.K_RANGE
        assert gamma_lo - 1e-9 <= params.gamma <= gamma_hi + 1e-9
        assert 1.0 / params.K - 1e-9 <= params.w_max <= config.W_MAX_HI + 1e-9
        assert tau_lo <= params.tau_hours <= tau_hi
        assert k_lo <= params.K <= k_hi
