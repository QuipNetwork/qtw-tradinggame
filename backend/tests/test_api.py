"""API surface via FastAPI TestClient: HTTP flow, 404s, and a WS push."""

from __future__ import annotations

import importlib.util
import itertools

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
_BASKET = [
    "BTC",
    "ETH",
    "SOL",
    "USDC",
    "IONQ",
    "QBTS",
    "RGTI",
    "IBM",
    "GOOGL",
    "NVDA",
    "MSFT",
    "AMZN",
    "HON",
    "SAF",
    "SPCX",
]
_ALT_BASKET = [
    "BNB",
    "XRP",
    "USDT",
    "DOGE",
    "HYPE",
    "ZEC",
    "ALGO",
    "FIL",
    "RENDER",
    "STRK",
    "ARQQ",
    "LAES",
    "QUBT",
    "IBM",
    "SPCX",
]


_email_seq = itertools.count()


def _create(client: TestClient, name: str = "Neo") -> str:
    response = client.post(
        "/agents",
        json={
            "name": name,
            # Unique per call so the one-agent-per-email guard never collides across
            # helper-created agents within a single test.
            "email": f"{name.lower()}{next(_email_seq)}@example.com",
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


def test_create_agent_sends_signup_confirmation_for_update_opt_in(monkeypatch):
    from backend.api import routes

    sent: list[dict[str, object]] = []

    def capture_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(routes, "send_signup_confirmation", capture_send)

    with TestClient(create_app()) as client:
        response = client.post(
            "/agents",
            json={
                "name": "Mail",
                "email": "mail@example.com",
                "updatesOptIn": True,
                "updateFrequency": "daily",
                "sliders": _SLIDERS,
                "assets": _BASKET,
            },
        )

    assert response.status_code == 200
    assert len(sent) == 1
    call = sent[0]
    assert call["to"] == "mail@example.com"
    assert call["name"] == "Mail"
    assert call["updates_opt_in"] is True
    assert "/p/" in call["link"] and "#t=" in call["link"]


def test_create_agent_sends_signup_email_even_without_update_opt_in(monkeypatch):
    from backend.api import routes

    sent: list[dict[str, object]] = []
    monkeypatch.setattr(routes, "send_signup_confirmation", lambda **kwargs: sent.append(kwargs))

    with TestClient(create_app()) as client:
        response = client.post(
            "/agents",
            json={
                "name": "NoMail",
                "email": "nomail@example.com",
                "updatesOptIn": False,
                "sliders": _SLIDERS,
                "assets": _BASKET,
            },
        )

    assert response.status_code == 200
    # The signup+link email is transactional (their way back to the agent), so it
    # still sends to a non-opter — just flagged updates_opt_in=False for the copy.
    assert len(sent) == 1
    assert sent[0]["to"] == "nomail@example.com"
    assert sent[0]["updates_opt_in"] is False
    assert "/p/" in sent[0]["link"] and "#t=" in sent[0]["link"]


def test_create_agent_email_failure_does_not_fail_signup(monkeypatch):
    from backend.api import routes

    def fail_send(**kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(routes, "send_signup_confirmation", fail_send)

    with TestClient(create_app()) as client:
        response = client.post(
            "/agents",
            json={
                "name": "Resilient",
                "email": "resilient@example.com",
                "updatesOptIn": True,
                "updateFrequency": "hourly",
                "sliders": _SLIDERS,
                "assets": _BASKET,
            },
        )

    assert response.status_code == 200
    assert response.json()["agentId"]


def test_patch_agent_persists_basket_without_optimizing():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        response = client.patch(f"/agents/{agent_id}", json={"assets": _ALT_BASKET})
        assert response.status_code == 200
        assert response.json()["assets"] == _ALT_BASKET

        got = client.get(f"/agents/{agent_id}")
        assert got.status_code == 200
        assert got.json()["assets"] == _ALT_BASKET


def test_patch_agent_rejects_unknown_or_too_small_basket():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        assert client.patch("/agents/nope", json={"assets": _ALT_BASKET}).status_code == 404

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
            json={
                "name": "Auth",
                "email": "auth@example.com",
                "sliders": _SLIDERS,
                "assets": _BASKET,
            },
        ).json()
        agent_id, token = body["agentId"], body["token"]
        good = {"Authorization": f"Bearer {token}"}

        # No token → 401 on every per-agent route.
        assert client.get(f"/agents/{agent_id}").status_code == 401
        assert client.post(f"/agents/{agent_id}/optimize", json={}).status_code == 401
        assert client.patch(f"/agents/{agent_id}", json={"assets": _BASKET}).status_code == 401
        assert client.get(f"/agents/{agent_id}/valuation-history").status_code == 401
        # Wrong token → 403.
        assert (
            client.get(f"/agents/{agent_id}", headers={"Authorization": "Bearer wrong"}).status_code
            == 403
        )
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


def test_routing_stats_recent_reports_tie_not_false_speed_win():
    # The TV bug: SA and D-Wave both ~0.10s with the SAME objective (quality tie), SA marginally
    # faster → the recent feed must report a TIE, not "3% faster than QPU" (sub-noise timing).
    jobs = get_job_store()
    job = jobs.record(
        "a1",
        ProviderProvenance(
            provider="sa", provider_role="CPU", q_hash="c" * 64,
            deadline_s=3.0, solve_time_s=0.103, feasible=True,
        ),
    )
    jobs.record_solve_snapshot(
        job_id=job.id, agent_id="a1", sliders=_SLIDERS, assets=_BASKET,
        portfolio=[{"ticker": "BTC", "pct": 100.0, "usd": 10_000.0}], holdings_units={"BTC": 1.0},
        solver_results=[
            {"provider": "sa", "providerRole": "CPU", "solveTime": 0.103, "objective": 0.00009},
            {"provider": "dwave", "providerRole": "QPU", "solveTime": 0.106, "objective": 0.00009},
        ],
        winner_provider="sa",
    )
    with TestClient(create_app()) as client:
        body = client.get("/routing-stats").json()
        assert body["recent"][0]["outcome"] == "tie"


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


def test_public_valuation_history_is_token_free_and_excludes_hidden():
    # The booth TV draws the spotlight sparkline from this PUBLIC endpoint — it
    # holds no owner token for other agents. Same series as the token-gated route,
    # carrying only total/pl over time (no holdings/PII).
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        store = get_agent_store()
        store.record_valuation_snapshot(
            agent_id,
            AgentUpdate(plUSD=100.0, plPct=1.0, total=10_100.0, asOf="2026-06-17T12:00:00Z", holdings=[]),
        )
        store.set_valuation(
            agent_id,
            AgentUpdate(plUSD=125.0, plPct=1.25, total=10_125.0, asOf="2026-06-17T12:01:00Z", holdings=[]),
        )

        # No Authorization header → still served (unlike /agents/{id}/valuation-history).
        client.headers.pop("Authorization", None)
        response = client.get(f"/leaderboard/{agent_id}/history")
        assert response.status_code == 200
        assert [point["total"] for point in response.json()] == [10_100.0, 10_125.0]

        # Admin-hidden agents 404 here too (consistent with the public leaderboard).
        store.set_flags(agent_id, hidden=True, disabled=False)
        assert client.get(f"/leaderboard/{agent_id}/history").status_code == 404
        # Unknown agent → 404.
        assert client.get("/leaderboard/does-not-exist/history").status_code == 404


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
        body = {"name": "Spam", "sliders": _SLIDERS, "assets": _BASKET}
        # Distinct emails so the per-IP limit (not the one-per-email guard) is what trips.
        for i in range(3):
            r = client.post("/agents", json={**body, "email": f"spam{i}@example.com"})
            assert r.status_code == 200
        blocked = client.post("/agents", json={**body, "email": "spam-x@example.com"})
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0


def test_rate_limit_keys_on_real_ip_not_spoofable_forwarded_for(monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_RATE_PER_IP", 2)
    with TestClient(create_app()) as client:
        body = {"name": "Spoof", "sliders": _SLIDERS, "assets": _BASKET}
        real = {"X-Real-IP": "5.5.5.5"}  # what Caddy sets (trusted, overwritten)
        # Varying the client-supplied X-Forwarded-For must NOT escape the bucket.
        for i in range(2):
            r = client.post(
                "/agents",
                json={**body, "email": f"spoof{i}@example.com"},
                headers={**real, "X-Forwarded-For": f"1.2.3.{i}"},
            )
            assert r.status_code == 200
        blocked = client.post(
            "/agents",
            json={**body, "email": "spoof-x@example.com"},
            headers={**real, "X-Forwarded-For": "9.9.9.9"},
        )
        assert blocked.status_code == 429  # same X-Real-IP → same bucket


def test_create_agent_rejects_duplicate_email():
    with TestClient(create_app()) as client:
        body = {"name": "First", "email": "dup@example.com", "sliders": _SLIDERS, "assets": _BASKET}
        assert client.post("/agents", json=body).status_code == 200
        # Case-insensitive: same address, different case + name → 409.
        again = {**body, "name": "Second", "email": "DUP@example.com"}
        resp = client.post("/agents", json=again)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]


def test_create_agent_requires_kiosk_key_when_configured(monkeypatch):
    monkeypatch.setattr(config, "KIOSK_SIGNUP_KEY", "s3cret")
    with TestClient(create_app()) as client:
        body = {"name": "Gated", "email": "gate@example.com", "sliders": _SLIDERS, "assets": _BASKET}
        assert client.post("/agents", json=body).status_code == 403  # no key
        assert client.post("/agents", json=body, headers={"X-Kiosk-Key": "wrong"}).status_code == 403
        ok = client.post("/agents", json=body, headers={"X-Kiosk-Key": "s3cret"})
        assert ok.status_code == 200


def test_kiosk_signups_skip_per_ip_limit(monkeypatch):
    monkeypatch.setattr(config, "KIOSK_SIGNUP_KEY", "s3cret")
    monkeypatch.setattr(config, "SIGNUP_RATE_PER_IP", 1)
    with TestClient(create_app()) as client:
        headers = {"X-Kiosk-Key": "s3cret"}
        body = {"name": "Booth", "sliders": _SLIDERS, "assets": _BASKET}
        # A second keyed signup from the same IP would 429 if the per-IP cap applied —
        # the trusted kiosk skips it (booth tablet / shared WiFi is one IP).
        r1 = client.post("/agents", json={**body, "email": "a@example.com"}, headers=headers)
        r2 = client.post("/agents", json={**body, "email": "b@example.com"}, headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200


@requires_gurobi
def test_optimize_accepts_a_new_basket():
    with TestClient(create_app()) as client:
        agent_id = _create(client)
        client.post(f"/agents/{agent_id}/optimize", json={})
        response = client.post(f"/agents/{agent_id}/optimize", json={"assets": _ALT_BASKET})
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "retune"
        assert {e["ticker"] for e in body["portfolio"]} == set(_ALT_BASKET)

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
