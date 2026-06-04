"""In-memory stores: agent lifecycle, valuation, and leaderboard ranking."""

from __future__ import annotations

import pytest

from backend.api.schemas import AgentConfig, AgentUpdate, SliderValues
from backend.persistence.agents import get_agent_store
from backend.persistence.leaderboard import build_leaderboard


def _config(name: str) -> AgentConfig:
    return AgentConfig(
        name=name,
        handle=name.lower(),
        sliders=SliderValues(
            tradingActivity=50,
            riskPreference=50,
            tradeSize=50,
            holdingStyle=50,
            diversification=50,
        ),
    )


def test_create_and_get_roundtrip():
    store = get_agent_store()
    record = store.create(_config("Alice"), bankroll=10_000.0)
    assert store.get(record.id) is record
    assert record.total == 10_000.0  # starts at bankroll
    assert store.get("missing") is None


def test_apply_solve_updates_holdings_and_count():
    store = get_agent_store()
    record = store.create(_config("Bob"), bankroll=10_000.0)
    store.apply_solve(record.id, {"BTC": 0.1}, total=11_000.0, provider_type="QPU")
    updated = store.get(record.id)
    assert updated.holdings_units == {"BTC": 0.1}
    assert updated.pl_usd == pytest.approx(1_000.0)
    assert updated.pl_pct == pytest.approx(10.0)
    assert updated.jobs_solved == 1
    assert updated.primary_provider == "QPU"


def test_leaderboard_ranks_by_total_descending():
    store = get_agent_store()
    low = store.create(_config("Low"), bankroll=10_000.0)
    high = store.create(_config("High"), bankroll=10_000.0)
    store.set_valuation(low.id, AgentUpdate(pl_usd=-500.0, pl_pct=-5.0, total=9_500.0))
    store.set_valuation(high.id, AgentUpdate(pl_usd=2_000.0, pl_pct=20.0, total=12_000.0))

    board = build_leaderboard(store)
    assert [e.agent_id for e in board] == [high.id, low.id]
    assert board[0].rank == 1
    assert board[0].total == pytest.approx(12_000.0)
