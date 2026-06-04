"""End-to-end optimize pipeline on the synthetic market (first solve + retune)."""

from __future__ import annotations

import importlib.util

import pytest

from backend.api.schemas import AgentConfig, SliderValues
from backend.financial.slider_map import map_sliders
from backend.orchestration.job import run_optimization
from backend.persistence.agents import get_agent_store

# The pipeline needs a feasible solver; Gurobi is the reliable one for N=15.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("gurobipy") is None, reason="gurobipy not installed"
)


def _config(**sliders: int) -> AgentConfig:
    base = {
        "tradingActivity": 50,
        "riskPreference": 50,
        "tradeSize": 50,
        "holdingStyle": 50,
        "diversification": 50,
    }
    base.update(sliders)
    return AgentConfig(name="Quanta", handle="q", sliders=SliderValues(**base))


def test_first_solve_allocates_bankroll():
    store = get_agent_store()
    config = _config(diversification=50)
    record = store.create(config, bankroll=10_000.0)

    outcome = run_optimization(record.id)
    result = outcome.result

    assert result.kind == "first"
    expected_k = map_sliders(config.sliders).K
    assert len(result.portfolio) == expected_k
    assert sum(e.pct for e in result.portfolio) == pytest.approx(100.0, abs=1e-6)
    assert sum(e.usd for e in result.portfolio) == pytest.approx(10_000.0, abs=1e-3)
    assert result.job_id and result.solved_at
    assert result.fee_usd == 0.0  # V0

    persisted = store.get(record.id)
    assert persisted.jobs_solved == 1
    assert persisted.holdings_units  # now holds positions

    # First solve emits an immediate valuation plus a new-agent TV splash.
    channels = {e.channel for e in outcome.events}
    assert f"agent:{record.id}" in channels
    assert "tv" in channels


def test_retune_is_value_neutral_and_marked():
    store = get_agent_store()
    record = store.create(_config(), bankroll=10_000.0)
    run_optimization(record.id)  # first solve

    outcome = run_optimization(
        record.id, sliders=_config(riskPreference=90, diversification=80).sliders
    )
    result = outcome.result

    assert result.kind == "retune"
    # Fixed-clock market → stationary spot → retune conserves value.
    assert sum(e.usd for e in result.portfolio) == pytest.approx(10_000.0, abs=1e-2)
    assert store.get(record.id).jobs_solved == 2
    # Retune emits only the per-agent valuation, no new-agent splash.
    assert {e.channel for e in outcome.events} == {f"agent:{record.id}"}
