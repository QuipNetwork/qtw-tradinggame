"""slider_map: the risk inversion, basket-relative caps, rebalance tiers."""

from __future__ import annotations

import pytest

from backend import config
from backend.api.schemas import SliderValues
from backend.financial.qubo_encoder import units_for_cardinality
from backend.financial.slider_map import map_sliders, max_position_cap, rebalance_every_hours


def _sliders(**overrides: float) -> SliderValues:
    base = {"rebalanceFrequency": 50, "riskPreference": 50, "maxPositionSize": 50}
    base.update(overrides)
    return SliderValues(**base)


def test_risk_preference_is_inverted():
    aggressive = map_sliders(_sliders(riskPreference=100), basket_size=10)
    conservative = map_sliders(_sliders(riskPreference=0), basket_size=10)
    gamma_lo, gamma_hi = config.GAMMA_RANGE
    assert aggressive.gamma == pytest.approx(gamma_lo, rel=1e-6)
    assert conservative.gamma == pytest.approx(gamma_hi, rel=1e-6)


def test_max_position_is_relative_to_basket(monkeypatch):
    # the raw relative cap is the convex mapping; method3 adds grid-aware clamps
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "convex")
    n = 10
    low = map_sliders(_sliders(maxPositionSize=0), basket_size=n)
    high = map_sliders(_sliders(maxPositionSize=100), basket_size=n)
    assert low.w_max == pytest.approx(1.0 / n)  # equal weight
    assert high.w_max == pytest.approx(config.W_MAX_CEILING)


def test_single_asset_basket_cap_is_100pct():
    assert max_position_cap(1, 0) == pytest.approx(1.0)
    assert max_position_cap(1, 100) == pytest.approx(1.0)


def test_rebalance_tiers_are_discrete_with_hourly_cap():
    assert rebalance_every_hours(0) == 24
    assert rebalance_every_hours(19) == 24
    assert rebalance_every_hours(20) == 8
    assert rebalance_every_hours(50) == 4
    assert rebalance_every_hours(99) == 1
    assert rebalance_every_hours(100) == 1  # hard cap


def test_w_min_keeps_budget_feasible(monkeypatch):
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "convex")
    for n in (1, 4, 25):
        params = map_sliders(_sliders(), basket_size=n)
        assert params.w_min == pytest.approx(config.MIN_POSITION_FRACTION / n)
        assert n * params.w_min <= 1.0
        assert n * params.w_max >= 1.0 - 1e-9


def test_min_position_floor_is_quarter_of_equal_weight(monkeypatch):
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "convex")
    params = map_sliders(_sliders(), basket_size=8)
    assert params.w_min == pytest.approx(0.25 / 8)


def test_convex_mode_leaves_cardinality_none(monkeypatch):
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "convex")
    params = map_sliders(_sliders(holdCount=3), basket_size=8)
    assert params.cardinality_k is None
    assert params.n_units_M is None and params.u_min_units is None


def test_method3_sets_grid_and_cardinality(monkeypatch):
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "method3")
    params = map_sliders(_sliders(holdCount=4), basket_size=10)
    assert params.cardinality_k == 4
    # M is the smallest power of two ≥ K (floored at MIN); K=4 → M=8.
    assert params.n_units_M == units_for_cardinality(4)
    assert params.n_units_M >= params.cardinality_k
    assert params.u_min_units == config.METHOD3_U_MIN
    assert params.w_min == pytest.approx(config.METHOD3_U_MIN / params.n_units_M)


def test_method3_cardinality_clamps_to_basket(monkeypatch):
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "method3")
    assert map_sliders(_sliders(holdCount=99), basket_size=8).cardinality_k == 8
    assert map_sliders(_sliders(holdCount=2), basket_size=8).cardinality_k == 2
    assert map_sliders(_sliders(), basket_size=8).cardinality_k == 8  # None → hold all


def test_method3_w_max_is_k_dominant_grid_aware(monkeypatch):
    monkeypatch.setattr(config, "OPTIMIZATION_MODE", "method3")
    # A low cap slider can't make the INTEGER budget unreachable: w_max is raised to the
    # grid-aware floor ⌈M/K⌉/M, STRICTER than 1/K. K=3 → M=8 → ⌈8/3⌉/8 = 3/8 vs 1/K = 1/3,
    # so this only passes with the grid-aware cap, not a plain 1/K one.
    params = map_sliders(_sliders(maxPositionSize=0, holdCount=3), basket_size=20)
    assert params.n_units_M == 8
    assert params.w_max == pytest.approx(3 / 8)  # ⌈M/K⌉/M, not 1/K = 0.333
    # held units can actually reach the budget: K · floor(w_max·M) ≥ M
    assert params.cardinality_k * int(params.w_max * params.n_units_M) >= params.n_units_M


def test_basket_below_minimum_raises():
    from backend.financial.basket import TICKERS, validate_basket

    with pytest.raises(ValueError, match="at least"):
        validate_basket(["BTC", "ETH"])
    assert validate_basket(["BTC", "ETH", "IONQ"]) == ["BTC", "ETH", "IONQ"]
    assert len(validate_basket(None)) == len(TICKERS)
