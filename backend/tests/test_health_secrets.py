"""Regression: /healthz reports only safe indicators, never secret VALUES.

Guards against a future change surfacing the DATABASE_URL (password) or the D-Wave token
in the health payload — it must stay booleans/enums (persistence, qpu_configured).
"""

from __future__ import annotations

import asyncio

from backend import config
from backend.api.routes import healthz


def test_healthz_does_not_leak_secret_values(monkeypatch):
    monkeypatch.setattr(
        config, "DATABASE_URL", "postgresql://admin:SUPERSECRET@db.internal:5432/prod"
    )
    monkeypatch.setenv("DWAVE_API_TOKEN", "tok-DEADBEEF-secret")

    dumped = asyncio.run(healthz()).model_dump_json()

    assert "SUPERSECRET" not in dumped  # DB password never surfaced
    assert "db.internal" not in dumped  # nor the DSN host
    assert "DEADBEEF" not in dumped  # token value never surfaced


def test_healthz_still_reports_configured_state(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://admin:pw@host/db")
    monkeypatch.setenv("DWAVE_API_TOKEN", "tok")
    resp = asyncio.run(healthz())
    assert resp.persistence == "sql"  # DB configured — as a boolean-ish enum, not the URL
    assert resp.qpu_configured is True  # QPU configured — as a bool, not the token

    monkeypatch.setattr(config, "DATABASE_URL", None)
    monkeypatch.delenv("DWAVE_API_TOKEN", raising=False)
    resp = asyncio.run(healthz())
    assert resp.persistence == "memory"
    assert resp.qpu_configured is False
