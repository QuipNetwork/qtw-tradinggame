from __future__ import annotations

import logging

import pytest

from backend.notifications import email as email_mod


class CaptureProvider:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        self.sent.append({"to": to, "subject": subject, "html": html, "text": text})


def test_send_portfolio_update_uses_registered_provider():
    provider = CaptureProvider()
    email_mod.set_email_provider(provider)
    try:
        email_mod.send_portfolio_update(
            to="player@example.com",
            name="Ada",
            total=10_250.0,
            pl_usd=250.0,
            pl_pct=2.5,
        )
    finally:
        email_mod.set_email_provider(email_mod.NoopEmailProvider())

    assert provider.sent == [
        {
            "to": "player@example.com",
            "subject": "Ada: your agent is +$250 (+2.50%)",
            "html": provider.sent[0]["html"],
            "text": provider.sent[0]["text"],
        }
    ]
    assert "Quip Network trading agent at Quantum.Tech World" in provider.sent[0]["text"]
    assert "$10,250" in provider.sent[0]["html"]
    assert "quip.network/images/brand/quip-network-lockup" in provider.sent[0]["html"]


def test_signup_confirmation_includes_link():
    provider = CaptureProvider()
    email_mod.set_email_provider(provider)
    try:
        email_mod.send_signup_confirmation(
            to="player@example.com",
            name="Ada",
            link="https://qtw.example/p/abcd1234#t=deadbeef",
            updates_opt_in=True,
        )
    finally:
        email_mod.set_email_provider(email_mod.NoopEmailProvider())

    assert provider.sent[0]["to"] == "player@example.com"
    assert provider.sent[0]["subject"] == "Ada, your Quip Network agent is live"
    assert "trading agent at Quantum.Tech World is live" in provider.sent[0]["text"]
    assert "$10,000" in provider.sent[0]["html"]
    assert "quip.network/images/brand/quip-network-lockup" in provider.sent[0]["html"]  # masthead
    assert "https://qtw.example/p/abcd1234#t=deadbeef" in provider.sent[0]["text"]
    assert "abcd1234#t=deadbeef" in provider.sent[0]["html"]


def test_signup_opt_out_includes_one_time_line_opt_in_does_not():
    link = "https://x/p/a#t=b"
    out = email_mod.render_signup_email(name="Ada", link=link, updates_opt_in=False)
    assert "one-time link" in out.text
    assert "won't email you again" in out.text
    opted_in = email_mod.render_signup_email(name="Ada", link=link, updates_opt_in=True)
    assert "one-time link" not in opted_in.text


def test_email_templates_escape_names_and_strip_control_characters():
    email = email_mod.render_signup_email(
        name="<b>Ada</b>\r\nBcc: bad@example.com",
        link="https://qtw.example/p/abcd1234#t=deadbeef",
    )

    assert "\r" not in email.subject
    assert "\n" not in email.subject
    assert "Bcc:" in email.subject
    assert "<b>Ada</b>" not in email.html
    assert "&lt;b&gt;Ada&lt;/b&gt;" in email.html


def test_noop_provider_does_not_log_recipient_or_subject(caplog):
    provider = email_mod.NoopEmailProvider()

    with caplog.at_level(logging.INFO, logger=email_mod.logger.name):
        provider.send(
            to="private@example.com",
            subject="Private Subject",
            html="<p>Hello</p>",
            text="Hello",
        )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "private@example.com" not in logged
    assert "Private Subject" not in logged
    assert "suppressed" in logged


def test_resend_provider_posts_to_resend_api(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(email_mod.httpx, "post", fake_post)

    provider = email_mod.ResendEmailProvider(
        api_key="re_test_key",
        sender="Quip Network <noreply@quip.network>",
        timeout_s=5.0,
    )
    provider.send(
        to="player@example.com",
        subject="Your agent is live",
        html="<p>Hello</p>",
        text="Hello",
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"
    assert captured["timeout"] == 5.0
    assert captured["json"]["from"] == "Quip Network <noreply@quip.network>"
    assert captured["json"]["to"] == ["player@example.com"]
    assert captured["json"]["subject"] == "Your agent is live"
    assert captured["json"]["html"] == "<p>Hello</p>"
    assert captured["json"]["text"] == "Hello"


def test_resend_provider_rejects_header_line_breaks(monkeypatch):
    def fake_post(*args, **kwargs):
        raise AssertionError("Resend should not be called for unsafe headers")

    monkeypatch.setattr(email_mod.httpx, "post", fake_post)

    provider = email_mod.ResendEmailProvider(
        api_key="re_test_key",
        sender="Quip Network <noreply@quip.network>",
    )
    with pytest.raises(ValueError, match="subject"):
        provider.send(
            to="player@example.com",
            subject="Hello\r\nBcc: bad@example.com",
            html="<p>Hello</p>",
            text="Hello",
        )
