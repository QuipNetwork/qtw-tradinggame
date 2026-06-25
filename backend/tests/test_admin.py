"""Admin dashboard API: the ADMIN_API_KEY gate, listing every agent (incl.
hidden ones with their email), and the hide/disable controls — including the
`disabled implies hidden` invariant and the disabled-agent solve lock."""

from __future__ import annotations

import itertools

from fastapi.testclient import TestClient

from backend import config
from backend.api.app import create_app
from backend.persistence.leaderboard import build_leaderboard

_SLIDERS = {"rebalanceFrequency": 50, "riskPreference": 70, "maxPositionSize": 50}
_BASKET = [
    "BTC", "ETH", "SOL", "USDC", "IONQ", "QBTS", "RGTI", "IBM",
    "GOOGL", "NVDA", "MSFT", "AMZN", "HON", "SAF", "SPCX",
]
_KEY = "test-admin-key"
_email_seq = itertools.count()


def _create(client: TestClient, name: str = "Neo") -> tuple[str, str]:
    resp = client.post(
        "/agents",
        json={
            "name": name,
            "email": f"{name.lower()}{next(_email_seq)}@example.com",
            "sliders": _SLIDERS,
            "assets": _BASKET,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["agentId"], body["token"]


def _admin(client: TestClient, method: str, path: str, **kw):
    return client.request(method, path, headers={"X-Admin-Key": _KEY}, **kw)


def test_admin_disabled_when_key_unset():
    # ADMIN_API_KEY unset → the dashboard is off (403), even with a header.
    with TestClient(create_app()) as client:
        assert client.get("/admin/agents").status_code == 403
        assert client.get(
            "/admin/agents", headers={"X-Admin-Key": "anything"}
        ).status_code == 403


def test_admin_requires_matching_key(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", _KEY)
    with TestClient(create_app()) as client:
        assert client.get("/admin/agents").status_code == 403  # no header
        assert client.get(
            "/admin/agents", headers={"X-Admin-Key": "wrong"}
        ).status_code == 403
        assert _admin(client, "GET", "/admin/agents").status_code == 200


def test_admin_lists_all_agents_with_email_and_flags(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", _KEY)
    with TestClient(create_app()) as client:
        a, _ = _create(client, "Alpha")
        b, _ = _create(client, "Beta")
        rows = _admin(client, "GET", "/admin/agents").json()
        assert {r["agentId"] for r in rows} == {a, b}
        for r in rows:
            assert r["email"]  # admin sees the email
            assert r["hidden"] is False and r["disabled"] is False
            assert r["rank"] in (1, 2)
            assert r["jobsSolved"] == 0  # retunes = solve count


def test_hide_removes_from_leaderboard_and_unhide_restores(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", _KEY)
    with TestClient(create_app()) as client:
        a, _ = _create(client, "Alpha")
        _create(client, "Beta")
        assert any(e.agent_id == a for e in build_leaderboard())

        r = _admin(client, "PATCH", f"/admin/agents/{a}", json={"hidden": True})
        assert r.status_code == 200
        assert r.json()["hidden"] is True and r.json()["rank"] is None
        assert all(e.agent_id != a for e in build_leaderboard())

        r = _admin(client, "PATCH", f"/admin/agents/{a}", json={"hidden": False})
        assert r.json()["hidden"] is False
        assert any(e.agent_id == a for e in build_leaderboard())


def test_disable_requires_hidden(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", _KEY)
    with TestClient(create_app()) as client:
        a, _ = _create(client, "Alpha")
        # disabling a visible agent is rejected
        assert _admin(
            client, "PATCH", f"/admin/agents/{a}", json={"disabled": True}
        ).status_code == 400

        # hide first, then disable
        _admin(client, "PATCH", f"/admin/agents/{a}", json={"hidden": True})
        r = _admin(client, "PATCH", f"/admin/agents/{a}", json={"disabled": True})
        assert r.status_code == 200 and r.json()["disabled"] is True

        # or hide + disable in one call
        b, _ = _create(client, "Beta")
        r = _admin(
            client, "PATCH", f"/admin/agents/{b}", json={"hidden": True, "disabled": True}
        )
        assert r.status_code == 200 and r.json()["hidden"] and r.json()["disabled"]


def test_unhide_clears_disabled(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", _KEY)
    with TestClient(create_app()) as client:
        a, _ = _create(client, "Alpha")
        _admin(
            client, "PATCH", f"/admin/agents/{a}", json={"hidden": True, "disabled": True}
        )
        r = _admin(client, "PATCH", f"/admin/agents/{a}", json={"hidden": False})
        assert r.json()["hidden"] is False and r.json()["disabled"] is False


def test_disabled_agent_cannot_retune(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", _KEY)
    with TestClient(create_app()) as client:
        agent_id, token = _create(client, "Gamma")
        _admin(
            client, "PATCH", f"/admin/agents/{agent_id}",
            json={"hidden": True, "disabled": True},
        )
        r = client.post(
            f"/agents/{agent_id}/optimize",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert r.status_code == 403
        assert "disabled" in r.json()["detail"]
