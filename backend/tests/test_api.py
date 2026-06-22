"""API surface via FastAPI TestClient: HTTP flow, 404s, and a WS push."""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import _check_required_config, create_app
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
    token = body["token"]
    assert body["qrUrl"] == f"https://qtw.quip.network/p/{body['agentId']}#t={token}"
    # Authorize subsequent per-agent calls on this client as the agent's owner.
    client.headers["Authorization"] = f"Bearer {token}"
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


def test_patch_agent_persists_basket_without_optimizing():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        response = client.patch(f"/agents/{agent_id}", json={"assets": ["HON", "GOOGL", "IBM"]})
        assert response.status_code == 200
        assert response.json()["assets"] == ["HON", "GOOGL", "IBM"]

        got = client.get(f"/agents/{agent_id}")
        assert got.status_code == 200
        assert got.json()["assets"] == ["HON", "GOOGL", "IBM"]


def test_patch_agent_rejects_unknown_or_too_small_basket():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        assert (
            client.patch("/agents/nope", json={"assets": ["HON", "GOOGL", "IBM"]}).status_code
            == 404
        )

        too_small = client.patch(f"/agents/{agent_id}", json={"assets": ["BTC"]})
        assert too_small.status_code == 422
        assert "at least" in too_small.json()["detail"]


def test_unknown_agent_is_404():
    with TestClient(create_app()) as client:
        assert client.get("/agents/nope").status_code == 404
        assert client.post("/agents/nope/optimize", json={}).status_code == 404


def test_per_agent_routes_require_owner_token():
    with TestClient(create_app()) as client:
        # Create directly (public) so this client carries no Authorization header.
        body = client.post(
            "/agents",
            json={"name": "Auth", "email": "auth@example.com", "sliders": _SLIDERS, "assets": _BASKET},
        ).json()
        agent_id, token = body["agentId"], body["token"]
        good = {"Authorization": f"Bearer {token}"}

        # No token → 401 on every per-agent route.
        assert client.get(f"/agents/{agent_id}").status_code == 401
        assert client.post(f"/agents/{agent_id}/optimize", json={}).status_code == 401
        assert client.patch(f"/agents/{agent_id}", json={"assets": _BASKET}).status_code == 401
        assert client.get(f"/agents/{agent_id}/valuation-history").status_code == 401
        # Wrong token → 403.
        assert client.get(f"/agents/{agent_id}", headers={"Authorization": "Bearer wrong"}).status_code == 403
        # Correct token → 200; email is returned only to the authorized owner.
        ok = client.get(f"/agents/{agent_id}", headers=good)
        assert ok.status_code == 200
        assert ok.json()["email"] == "auth@example.com"
        # Missing agent → 404 even with a valid-looking token.
        assert client.get("/agents/nope", headers=good).status_code == 404
        # The public leaderboard never exposes the email.
        board = client.get("/leaderboard").json()
        assert all("email" not in entry for entry in board)


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
    job = jobs.record(
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
    jobs.record_solve_snapshot(
        job_id=job.id,
        agent_id="a2",
        sliders=_SLIDERS,
        assets=_BASKET,
        portfolio=[{"ticker": "BTC", "pct": 100.0, "usd": 10_000.0}],
        holdings_units={"BTC": 1.0},
        solver_results=[
            {"provider": "sa", "solveTime": 0.21},
            {"provider": "dwave", "solveTime": 0.12},
        ],
        winner_provider="sa",
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
        assert body["recent"][0]["provider"] == "sa"
        assert body["recent"][0]["vsTime"] == 0.12


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
        token = client.headers["Authorization"].split(" ", 1)[1]
        client.post(f"/agents/{agent_id}/optimize", json={})
        with client.websocket_connect(f"/agents/{agent_id}?t={token}") as socket:
            client.post(f"/agents/{agent_id}/optimize", json={})  # retune → push
            update = socket.receive_json()
            assert {"plUSD", "plPct", "total", "holdings", "asOf", "stale"} <= set(update)
            assert {h["ticker"] for h in update["holdings"]} == set(_BASKET)


def test_agent_websocket_rejects_without_token():
    from starlette.websockets import WebSocketDisconnect

    with TestClient(create_app()) as client:
        body = client.post(
            "/agents",
            json={"name": "WS", "email": "ws@example.com", "sliders": _SLIDERS, "assets": _BASKET},
        ).json()
        agent_id = body["agentId"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/agents/{agent_id}"):  # no ?t= → 1008
                pass


def test_basket_below_minimum_is_rejected():
    with TestClient(create_app()) as client:
        response = client.post(
            "/agents",
            json={"name": "Tiny", "sliders": _SLIDERS, "assets": ["BTC"]},
        )
        assert response.status_code == 422
        assert "at least" in response.json()["detail"]


def test_signup_rate_limited_per_ip(monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_RATE_PER_IP", 3)
    with TestClient(create_app()) as client:
        body = {"name": "Spam", "email": "spam@example.com", "sliders": _SLIDERS, "assets": _BASKET}
        for _ in range(3):
            assert client.post("/agents", json=body).status_code == 200
        blocked = client.post("/agents", json=body)
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0


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


@pytest.mark.parametrize("env", ["production", "booth", "Production", " booth "])
def test_required_config_rejects_memory_for_real_deploys(monkeypatch, env):
    """production/booth must carry a DATABASE_URL — refuse to boot in-memory there."""
    monkeypatch.setattr(config, "APP_ENV", env)
    monkeypatch.setattr(config, "DATABASE_URL", None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _check_required_config()


@pytest.mark.parametrize(
    "env", ["local", "local-dev", "local-container", "local-smoke-azain", "dev", "test"]
)
def test_required_config_allows_local_memory(monkeypatch, env):
    """Any local/dev run may use in-memory persistence (no DATABASE_URL required)."""
    monkeypatch.setattr(config, "APP_ENV", env)
    monkeypatch.setattr(config, "DATABASE_URL", None)
    _check_required_config()  # no raise


def test_api_explorer_disabled_for_real_deploys(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "booth")
    assert create_app().openapi_url is None  # no /openapi.json, /docs, /redoc in prod
    monkeypatch.setattr(config, "APP_ENV", "local")
    assert create_app().openapi_url == "/openapi.json"  # kept locally
