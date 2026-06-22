"""API surface via FastAPI TestClient: HTTP flow, 404s, and a WS push."""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.schemas import AgentUpdate, QpuBudgetStatus
from backend.persistence.agents import get_agent_store
from backend.persistence.jobs import get_job_store
from backend.persistence.qpu_budget import QpuBudgetExceeded
from backend.solvers.types import ProviderProvenance

requires_gurobi = pytest.mark.skipif(
    importlib.util.find_spec("gurobipy") is None, reason="gurobipy not installed"
)

_SLIDERS = {"rebalanceFrequency": 50, "riskPreference": 70, "maxPositionSize": 50}
_BASKET = ["BTC", "ETH", "IONQ", "QBTS"]


def _create(client: TestClient, name: str = "Neo") -> str:
    response = client.post(
        "/agents",
        json={
            "name": name,
            "email": f"{name.lower()}@example.com",
            "sliders": _SLIDERS,
            "assets": _BASKET,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bankroll"] == 10_000.0
    assert body["qrUrl"] == f"https://qtw.quip.network/p/{body['agentId']}"
    return body["agentId"]


def test_healthz_reports_runtime_shape():
    with TestClient(create_app()) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["persistence"] == "memory"
        assert body["marketDataSource"] == "assets-api"
        assert body["qpuConfigured"] is False


def test_create_and_get_agent():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        got = client.get(f"/agents/{agent_id}")
        assert got.status_code == 200
        body = got.json()
        assert body["sliders"]["riskPreference"] == 70
        assert body["assets"] == _BASKET


def test_unknown_agent_is_404():
    with TestClient(create_app()) as client:
        assert client.get("/agents/nope").status_code == 404
        assert client.post("/agents/nope/optimize", json={}).status_code == 404


def test_optimize_qpu_budget_exhaustion_is_429(monkeypatch):
    from backend.api import routes

    status = QpuBudgetStatus(
        used=3,
        limit=3,
        windowSeconds=600,
        retryAfterSeconds=120,
        nextAvailableAt="2026-06-18T12:02:00+00:00",
    )

    def over_budget(agent_id, sliders=None, assets=None):
        raise QpuBudgetExceeded(status)

    monkeypatch.setattr(routes, "run_optimization", over_budget)

    with TestClient(create_app()) as client:
        agent_id = _create(client)
        response = client.post(f"/agents/{agent_id}/optimize", json={})
        assert response.status_code == 429
        assert response.headers["retry-after"] == "120"
        detail = response.json()["detail"]
        assert detail["retryAfterSeconds"] == 120
        assert detail["qpuBudget"]["used"] == 3


def test_optimize_market_data_unavailable_is_503(monkeypatch):
    from backend.api import routes
    from backend.financial.prices.assets_api import AssetsApiError

    def market_down(agent_id, sliders=None, assets=None):
        raise AssetsApiError("assets-api request failed: /v1/history: boom")

    monkeypatch.setattr(routes, "run_optimization", market_down)

    with TestClient(create_app()) as client:
        agent_id = _create(client)
        response = client.post(f"/agents/{agent_id}/optimize", json={})
        assert response.status_code == 503
        assert "v1/history" not in response.json()["detail"]  # internal path not leaked


def test_leaderboard_lists_created_agents():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        board = client.get("/leaderboard").json()
        assert any(entry["agentId"] == agent_id for entry in board)


def test_routing_stats_counts_recorded_winning_jobs():
    jobs = get_job_store()
    jobs.record(
        "a1",
        ProviderProvenance(
            provider="dwave",
            provider_role="QPU",
            q_hash="a" * 64,
            deadline_s=3.0,
            solve_time_s=0.12,
            feasible=True,
        ),
    )
    jobs.record(
        "a2",
        ProviderProvenance(
            provider="sa",
            provider_role="CPU",
            q_hash="b" * 64,
            deadline_s=3.0,
            solve_time_s=0.21,
            feasible=True,
        ),
    )

    with TestClient(create_app()) as client:
        response = client.get("/routing-stats")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["qpuWins"] == 1
        assert body["cpuWins"] == 1
        assert body["qpuPct"] == 50.0
        assert body["cpuPct"] == 50.0
        assert {provider["provider"] for provider in body["providers"]} == {"dwave", "sa"}


def test_valuation_history_returns_sampled_points_and_current_tail():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        store = get_agent_store()
        sampled = AgentUpdate(
            plUSD=100.0,
            plPct=1.0,
            total=10_100.0,
            asOf="2026-06-17T12:00:00Z",
            holdings=[],
        )
        current = AgentUpdate(
            plUSD=125.0,
            plPct=1.25,
            total=10_125.0,
            asOf="2026-06-17T12:01:00Z",
            holdings=[],
        )
        store.record_valuation_snapshot(agent_id, sampled)
        store.set_valuation(agent_id, current)

        response = client.get(f"/agents/{agent_id}/valuation-history")
        assert response.status_code == 200
        body = response.json()
        assert [point["total"] for point in body] == [10_100.0, 10_125.0]
        assert body[-1]["plPct"] == 1.25


@requires_gurobi
def test_optimize_returns_routing_result():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        response = client.post(f"/agents/{agent_id}/optimize", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "first"
        assert body["providerType"] in ("QPU", "CPU")
        assert {entry["ticker"] for entry in body["portfolio"]} == set(_BASKET)
        assert sum(entry["pct"] for entry in body["portfolio"]) == pytest.approx(100.0, abs=1e-6)


@requires_gurobi
def test_websocket_streams_agent_update():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        client.post(f"/agents/{agent_id}/optimize", json={})
        with client.websocket_connect(f"/agents/{agent_id}") as socket:
            client.post(f"/agents/{agent_id}/optimize", json={})  # retune → push
            update = socket.receive_json()
            assert {"plUSD", "plPct", "total", "holdings", "asOf", "stale"} <= set(update)
            assert {h["ticker"] for h in update["holdings"]} == set(_BASKET)


def test_basket_below_minimum_is_rejected():
    with TestClient(create_app()) as client:
        response = client.post(
            "/agents",
            json={"name": "Tiny", "sliders": _SLIDERS, "assets": ["BTC"]},
        )
        assert response.status_code == 422
        assert "at least" in response.json()["detail"]


@requires_gurobi
def test_optimize_accepts_a_new_basket():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        client.post(f"/agents/{agent_id}/optimize", json={})
        response = client.post(
            f"/agents/{agent_id}/optimize", json={"assets": ["HON", "GOOGL", "IBM"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "retune"
        assert {e["ticker"] for e in body["portfolio"]} == {"HON", "GOOGL", "IBM"}

        too_small = client.post(f"/agents/{agent_id}/optimize", json={"assets": ["BTC"]})
        assert too_small.status_code == 422
