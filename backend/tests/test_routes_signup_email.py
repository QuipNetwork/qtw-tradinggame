"""Signup confirmation email is transactional: it carries the agent link and
goes to anyone who provided an email, regardless of result-email opt-in."""

from __future__ import annotations

from backend.api import routes
from backend.api.schemas import AgentConfig, SliderValues
from backend.notifications import email as email_mod
from backend.persistence.agents import AgentStore


class CaptureProvider:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, to, subject, html, text) -> None:
        self.sent.append({"to": to, "html": html, "text": text})


def _record(*, email, opt_in):
    cfg = AgentConfig(
        name="Ada",
        email=email,
        updatesOptIn=opt_in,
        sliders=SliderValues(rebalanceFrequency=50, riskPreference=70, maxPositionSize=50),
        assets=["BTC", "ETH"],
    )
    return AgentStore().create(cfg, bankroll=10_000.0)


def test_signup_email_sent_to_non_opter_with_email():
    provider = CaptureProvider()
    email_mod.set_email_provider(provider)
    try:
        rec = _record(email="ada@example.com", opt_in=False)
        routes._send_signup_confirmation_email(rec, "deadbeef")
    finally:
        email_mod.set_email_provider(email_mod.NoopEmailProvider())

    assert provider.sent[0]["to"] == "ada@example.com"
    assert f"/p/{rec.id}#t=deadbeef" in provider.sent[0]["text"]
    assert "won't email you again" in provider.sent[0]["text"]


def test_signup_email_skipped_without_email():
    provider = CaptureProvider()
    email_mod.set_email_provider(provider)
    try:
        rec = _record(email=None, opt_in=True)
        routes._send_signup_confirmation_email(rec, "deadbeef")
    finally:
        email_mod.set_email_provider(email_mod.NoopEmailProvider())

    assert provider.sent == []
