"""retune: trade diffing and one-way turnover (value-neutral, no fee)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.retune import compute_retune

TICKERS = ["BTC", "ETH", "SOL", "IONQ"]


def test_first_solve_allocates_from_zero():
    w_old = np.zeros(4)
    w_new = np.array([0.5, 0.3, 0.2, 0.0])
    result = compute_retune(w_old, w_new, TICKERS, portfolio_value_usd=10_000.0)
    assert {t.ticker for t in result.trades} == {"BTC", "ETH", "SOL"}
    assert all(t.delta_usd > 0 for t in result.trades)
    assert sum(result.new_holdings_usd.values()) == pytest.approx(10_000.0)


def test_retune_produces_signed_trades_summing_to_zero():
    w_old = np.array([0.508, 0.299, 0.193, 0.0])
    w_new = np.array([0.30, 0.30, 0.0, 0.40])
    result = compute_retune(w_old, w_new, TICKERS, portfolio_value_usd=10_240.0)
    buys = sum(t.delta_usd for t in result.trades if t.delta_usd > 0)
    sells = sum(-t.delta_usd for t in result.trades if t.delta_usd < 0)
    assert buys == pytest.approx(sells)  # value-neutral


def test_one_way_turnover_is_half_the_l1_delta():
    w_old = np.array([0.5, 0.5, 0.0, 0.0])
    w_new = np.array([0.0, 0.5, 0.5, 0.0])
    result = compute_retune(w_old, w_new, TICKERS, portfolio_value_usd=10_000.0)
    assert result.one_way_turnover == pytest.approx(0.5)
