"""Throttled result-email dispatch: send at most one per opt-in window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.api.schemas import AgentConfig, SliderValues
from backend.notifications import dispatch
from backend.notifications import email as email_mod
from backend.persistence.agents import AgentStore


class CaptureProvider:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, *, to, subject, html, text) -> None:
        self.sent.append(to)


def _agent(store, *, opt_in=True, freq="hourly", email="p@example.com"):
    cfg = AgentConfig(
        name="Ada",
        email=email,
        updatesOptIn=opt_in,
        updateFrequency=freq,
        sliders=SliderValues(rebalanceFrequency=50, riskPreference=70, maxPositionSize=50),
        assets=["BTC", "ETH"],
    )
    return store.create(cfg, bankroll=10_000.0)


def _run(store, record, now):
    provider = CaptureProvider()
    email_mod.set_email_provider(provider)
    try:
        dispatch.maybe_send_update_email(record, now=now, store=store)
    finally:
        email_mod.set_email_provider(email_mod.NoopEmailProvider())
    return provider


def test_sends_when_no_prior_email():
    store = AgentStore()
    rec = _agent(store)
    rec.last_update_email_at = None
    now = datetime.now(UTC)
    assert _run(store, rec, now).sent == ["p@example.com"]
    assert store.get(rec.id).last_update_email_at == now.isoformat()


def test_skips_within_hourly_window():
    store = AgentStore()
    rec = _agent(store, freq="hourly")
    now = datetime.now(UTC)
    rec.last_update_email_at = (now - timedelta(minutes=30)).isoformat()
    assert _run(store, rec, now).sent == []


def test_sends_after_hourly_window_elapses():
    store = AgentStore()
    rec = _agent(store, freq="hourly")
    now = datetime.now(UTC)
    rec.last_update_email_at = (now - timedelta(minutes=61)).isoformat()
    assert _run(store, rec, now).sent == ["p@example.com"]


def test_daily_window_blocks_an_hour_in():
    store = AgentStore()
    rec = _agent(store, freq="daily")
    now = datetime.now(UTC)
    rec.last_update_email_at = (now - timedelta(hours=2)).isoformat()
    assert _run(store, rec, now).sent == []


def test_skips_when_not_opted_in_or_no_email():
    store = AgentStore()
    now = datetime.now(UTC)
    not_opted = _agent(store, opt_in=False)
    not_opted.last_update_email_at = None
    assert _run(store, not_opted, now).sent == []
    no_email = _agent(store, email=None)
    no_email.last_update_email_at = None
    assert _run(store, no_email, now).sent == []
