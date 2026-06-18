"""QPU budget: per-agent rolling-window admissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from backend.api.schemas import AgentConfig, SliderValues
from backend.orchestration import job
from backend.orchestration.job import run_optimization
from backend.persistence.agents import get_agent_store
from backend.persistence.db import DbQpuBudgetStore
from backend.persistence.qpu_budget import QpuBudgetExceeded, QpuBudgetStore
from backend.solvers.types import Solution


def test_qpu_budget_allows_three_attempts_per_rolling_window():
    store = QpuBudgetStore()
    now = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)

    for _ in range(3):
        status = store.reserve("a1", source="manual", now=now)

    assert status.used == 3
    assert status.retry_after_seconds == 600
    with pytest.raises(QpuBudgetExceeded) as exc:
        store.reserve("a1", source="manual", now=now)
    assert exc.value.status.retry_after_seconds == 600

    later = now + timedelta(seconds=601)
    assert store.reserve("a1", source="manual", now=later).used == 1


def test_qpu_budget_is_per_agent():
    store = QpuBudgetStore()
    now = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)

    for _ in range(3):
        store.reserve("a1", source="manual", now=now)

    assert store.reserve("a2", source="manual", now=now).used == 1


def test_db_qpu_budget_survives_reload(tmp_path):
    url = f"sqlite:///{tmp_path / 'budget.db'}"
    now = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    store = DbQpuBudgetStore(url, environment="local", allow_reset=True)

    store.reserve("agent", source="scheduled", now=now)
    store.reserve("agent", source="manual", now=now + timedelta(seconds=1))

    reloaded = DbQpuBudgetStore(url, environment="local", allow_reset=True)
    assert reloaded.status("agent", now=now + timedelta(seconds=2)).used == 2


def test_run_optimization_consumes_qpu_budget_when_dwave_configured(monkeypatch):
    store = get_agent_store()
    record = store.create(
        AgentConfig(
            name="Budget",
            email="budget@example.com",
            sliders=SliderValues(
                rebalanceFrequency=50,
                riskPreference=50,
                maxPositionSize=50,
            ),
            assets=["BTC", "ETH", "SOL"],
        ),
        bankroll=10_000.0,
    )
    budget = QpuBudgetStore()
    monkeypatch.setenv("DWAVE_API_TOKEN", "token")

    def fake_race(problem, deadline_s=None, *, include_qpu=True):
        assert include_qpu is True
        winner = Solution(
            weights=np.array([0.4, 0.3, 0.3]),
            objective=0.0,
            solve_time_s=0.1,
            provider="dwave",
            provider_role="QPU",
            feasible=True,
        )
        return SimpleNamespace(
            winner=winner,
            vs_classical=1.0,
            solver_runs=[],
            all_results=[winner],
            q_hash="q",
        )

    monkeypatch.setattr(job, "race", fake_race)

    for _ in range(3):
        result = run_optimization(record.id, qpu_budget=budget).result
        assert result.qpu_budget.used <= 3

    with pytest.raises(QpuBudgetExceeded):
        run_optimization(record.id, qpu_budget=budget)
    assert store.get(record.id).jobs_solved == 3
