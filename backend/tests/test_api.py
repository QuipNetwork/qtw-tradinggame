"""API surface via FastAPI TestClient: HTTP flow, 404s, and a WS push.

The TestClient context manager runs the app lifespan, which starts the MTM
scheduler. Gurobi is required for a feasible optimize; the WS/HTTP shape tests
that don't optimize run regardless.
"""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app

_HAS_GUROBI = importlib.util.find_spec("gurobipy") is not None
requires_gurobi = pytest.mark.skipif(not _HAS_GUROBI, reason="gurobipy not installed")

_SLIDERS = {
    "tradingActivity": 50,
    "riskPreference": 70,
    "tradeSize": 50,
    "holdingStyle": 40,
    "diversification": 50,
}


def _create(client: TestClient, name: str = "Neo") -> str:
    response = client.post(
        "/agents", json={"name": name, "handle": name.lower(), "sliders": _SLIDERS}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bankroll"] == 10_000.0
    assert body["qrUrl"].endswith(f"/p/{body['agentId']}")
    return body["agentId"]


def test_create_and_get_agent():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        got = client.get(f"/agents/{agent_id}")
        assert got.status_code == 200
        assert got.json()["sliders"]["riskPreference"] == 70


def test_unknown_agent_is_404():
    with TestClient(create_app()) as client:
        assert client.get("/agents/nope").status_code == 404
        assert client.post("/agents/nope/optimize", json={}).status_code == 404


def test_leaderboard_lists_created_agents():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        board = client.get("/leaderboard").json()
        assert any(entry["agentId"] == agent_id for entry in board)


@requires_gurobi
def test_optimize_returns_routing_result():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        response = client.post(f"/agents/{agent_id}/optimize", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "first"
        assert body["providerType"] in ("QPU", "CPU")
        assert sum(entry["pct"] for entry in body["portfolio"]) == pytest.approx(100.0, abs=1e-6)
        assert "vsClassical" in body and "solvedAt" in body


@requires_gurobi
def test_websocket_streams_agent_update():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        client.post(f"/agents/{agent_id}/optimize", json={})  # first solve → holdings
        with client.websocket_connect(f"/agents/{agent_id}") as socket:
            # A retune publishes an immediate valuation to the subscribed channel.
            client.post(f"/agents/{agent_id}/optimize", json={})
            update = socket.receive_json()
            assert {"plUSD", "plPct", "total"} <= set(update)
