"""In-memory stores: agent lifecycle, valuation, leaderboard ranking."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend import config
from backend.api.schemas import AgentConfig, AgentUpdate, SliderValues
from backend.persistence.agents import AgentStore, get_agent_store, set_agent_store
from backend.persistence.db import (
    DbAgentStore,
    DbJobStore,
    DbQpuBudgetStore,
    solve_snapshots_table,
    valuation_snapshots_table,
)
from backend.persistence.jobs import JobStore, get_job_store, set_job_store
from backend.persistence.leaderboard import build_leaderboard
from backend.persistence.qpu_budget import (
    QpuBudgetStore,
    get_qpu_budget_store,
    set_qpu_budget_store,
)
from backend.solvers.types import ProviderProvenance


def _config(name: str) -> AgentConfig:
    return AgentConfig(
        name=name,
        handle=name.lower(),
        email=f"{name.lower()}@example.com",
        sliders=SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50),
        assets=["BTC", "ETH"],
    )


def test_create_and_get_roundtrip():
    store = get_agent_store()
    record = store.create(_config("Alice"), bankroll=10_000.0)
    assert store.get(record.id) is record
    assert record.total == 10_000.0
    assert record.to_config().assets == ["BTC", "ETH"]
    assert record.to_config().email == "alice@example.com"
    assert store.get("missing") is None


def test_apply_solve_updates_holdings_and_count():
    store = get_agent_store()
    record = store.create(_config("Bob"), bankroll=10_000.0)
    store.apply_solve(record.id, {"BTC": 0.1}, total=11_000.0, provider_type="QPU")
    updated = store.get(record.id)
    assert updated.holdings_units == {"BTC": 0.1}
    assert updated.pl_usd == pytest.approx(1_000.0)
    assert updated.jobs_solved == 1
    assert updated.primary_provider == "QPU"
    assert updated.last_solved_at is not None
    assert updated.next_rebalance_at is not None
    assert updated.rebalance_interval_hours == 4
    assert datetime.fromisoformat(updated.next_rebalance_at) > datetime.fromisoformat(
        updated.last_solved_at
    )


def test_leaderboard_ranks_by_total_descending():
    store = get_agent_store()
    low = store.create(_config("Low"), bankroll=10_000.0)
    high = store.create(_config("High"), bankroll=10_000.0)
    store.set_valuation(low.id, AgentUpdate(plUSD=-500.0, plPct=-5.0, total=9_500.0))
    store.set_valuation(high.id, AgentUpdate(plUSD=2_000.0, plPct=20.0, total=12_000.0))

    board = build_leaderboard(store)
    assert [e.agent_id for e in board] == [high.id, low.id]
    assert board[0].rank == 1


def test_in_memory_valuation_history_includes_sampled_and_current_points():
    store = get_agent_store()
    agent = store.create(_config("Hist"), bankroll=10_000.0)
    first = AgentUpdate(
        plUSD=100.0,
        plPct=1.0,
        total=10_100.0,
        asOf="2026-06-17T12:00:00Z",
        holdings=[],
    )
    current = AgentUpdate(
        plUSD=140.0,
        plPct=1.4,
        total=10_140.0,
        asOf="2026-06-17T12:01:00Z",
        holdings=[],
    )

    store.record_valuation_snapshot(agent.id, first)
    store.set_valuation(agent.id, current)

    history = store.valuation_history(agent.id)
    assert [point.total for point in history] == [10_100.0, 10_140.0]
    assert history[-1].as_of == "2026-06-17T12:01:00Z"


def test_db_agent_store_hydrates_agents_and_holdings(tmp_path):
    url = f"sqlite:///{tmp_path / 'agents.db'}"
    store = DbAgentStore(url, environment="local", allow_reset=True)
    record = store.create(_config("Dora"), bankroll=10_000.0)
    store.update_assets(record.id, ["BTC", "ETH", "SOL"])
    store.update_sliders(
        record.id,
        SliderValues(rebalanceFrequency=80, riskPreference=20, maxPositionSize=65),
    )
    store.apply_solve(record.id, {"BTC": 0.25, "ETH": 1.5}, total=10_500.0, provider_type="CPU")

    reloaded = DbAgentStore(url, environment="local", allow_reset=True)
    got = reloaded.get(record.id)
    assert got is not None
    assert got.assets == ["BTC", "ETH", "SOL"]
    assert got.sliders.risk_preference == 20
    assert got.holdings_units == {"BTC": 0.25, "ETH": 1.5}
    assert got.total == 10_500.0
    assert got.jobs_solved == 1
    assert got.next_rebalance_at == record.next_rebalance_at
    assert got.rebalance_interval_hours == 1


def test_db_job_store_records_jobs_and_solve_snapshots(tmp_path):
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    agents = DbAgentStore(url, environment="local", allow_reset=True)
    jobs = DbJobStore(url, environment="local", allow_reset=True)
    agent = agents.create(_config("Eve"), bankroll=10_000.0)
    provenance = ProviderProvenance(
        provider="sa",
        provider_role="CPU",
        q_hash="a" * 64,
        deadline_s=3.0,
        solve_time_s=0.12,
        feasible=True,
    )

    job = jobs.record(agent.id, provenance)
    jobs.record_solve_snapshot(
        job_id=job.id,
        agent_id=agent.id,
        sliders=_config("Eve").sliders.model_dump(by_alias=True),
        assets=["BTC", "ETH"],
        portfolio=[{"ticker": "BTC", "pct": 50.0, "usd": 5_000.0}],
        holdings_units={"BTC": 0.1},
        solver_results=[{"provider": "sa", "feasible": True}],
        winner_provider="sa",
    )

    reloaded = DbJobStore(url, environment="local", allow_reset=True)
    assert reloaded.get(job.id) is not None
    assert reloaded.get(job.id).q_hash == "a" * 64
    assert reloaded.solve_snapshots() == []

    with jobs.engine.begin() as conn:
        rows = conn.execute(solve_snapshots_table.select()).mappings().all()
    assert rows[0]["winner_provider"] == "sa"
    assert rows[0]["assets"] == ["BTC", "ETH"]


def test_db_agent_store_records_sampled_valuation_snapshots(tmp_path):
    url = f"sqlite:///{tmp_path / 'valuations.db'}"
    store = DbAgentStore(url, environment="local", allow_reset=True)
    agent = store.create(_config("Val"), bankroll=10_000.0)
    update = AgentUpdate(
        plUSD=100.0,
        plPct=1.0,
        total=10_100.0,
        asOf="2026-06-17T12:00:00Z",
        stale=True,
        holdings=[],
    )

    store.record_valuation_snapshot(agent.id, update)

    with store.engine.begin() as conn:
        rows = conn.execute(valuation_snapshots_table.select()).mappings().all()
    assert rows[0]["agent_id"] == agent.id
    assert rows[0]["total"] == 10_100.0
    assert rows[0]["stale"] is True


def test_db_agent_store_reads_valuation_history_with_current_tail(tmp_path):
    url = f"sqlite:///{tmp_path / 'valuation_history.db'}"
    store = DbAgentStore(url, environment="local", allow_reset=True)
    agent = store.create(_config("Tail"), bankroll=10_000.0)
    sampled = AgentUpdate(
        plUSD=100.0,
        plPct=1.0,
        total=10_100.0,
        asOf="2026-06-17T12:00:00Z",
        holdings=[],
    )
    current = AgentUpdate(
        plUSD=175.0,
        plPct=1.75,
        total=10_175.0,
        asOf="2026-06-17T12:01:00Z",
        holdings=[],
    )

    store.record_valuation_snapshot(agent.id, sampled)
    store.set_valuation(agent.id, current)

    history = store.valuation_history(agent.id, limit=10)
    assert [point.total for point in history] == [10_100.0, 10_175.0]
    assert history[-1].pl_pct == pytest.approx(1.75)

    reloaded = DbAgentStore(url, environment="local", allow_reset=True)
    assert [point.total for point in reloaded.valuation_history(agent.id, limit=10)] == [10_100.0]


def test_database_url_selects_db_stores(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'selected.db'}"
    set_agent_store(None)
    set_job_store(None)
    set_qpu_budget_store(None)
    monkeypatch.setattr(config, "DATABASE_URL", url)
    monkeypatch.setattr(config, "APP_ENV", "local")

    assert isinstance(get_agent_store(), DbAgentStore)
    assert isinstance(get_job_store(), DbJobStore)
    assert isinstance(get_qpu_budget_store(), DbQpuBudgetStore)


def test_store_overrides_force_in_memory_even_with_database_url(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{tmp_path / 'unused.db'}")
    set_agent_store(AgentStore())
    set_job_store(JobStore())
    set_qpu_budget_store(QpuBudgetStore())

    assert isinstance(get_agent_store(), AgentStore)
    assert not isinstance(get_agent_store(), DbAgentStore)
    assert isinstance(get_job_store(), JobStore)
    assert not isinstance(get_job_store(), DbJobStore)
    assert isinstance(get_qpu_budget_store(), QpuBudgetStore)
    assert not isinstance(get_qpu_budget_store(), DbQpuBudgetStore)
