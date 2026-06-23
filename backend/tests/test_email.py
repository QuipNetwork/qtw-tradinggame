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
    assert "Quantum.Tech World" in provider.sent[0]["text"]
    assert "<strong>$10,250</strong>" in provider.sent[0]["html"]


def test_signup_confirmation_uses_registered_provider():
    provider = CaptureProvider()
    email_mod.set_email_provider(provider)
    try:
        email_mod.send_signup_confirmation(to="player@example.com", name="Ada")
    finally:
        email_mod.set_email_provider(email_mod.NoopEmailProvider())

    assert provider.sent[0]["to"] == "player@example.com"
    assert provider.sent[0]["subject"] == "Ada, your Quip Network agent is live"
    assert "trading agent is live" in provider.sent[0]["text"]
    assert "<strong>$10,000</strong>" in provider.sent[0]["html"]


def test_email_templates_escape_names_and_strip_control_characters():
    email = email_mod.render_signup_email(name="<b>Ada</b>\r\nBcc: bad@example.com")

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


def test_smtp_provider_sends_multipart_message_over_starttls(monkeypatch):
    class FakeSMTP:
        instances: list[FakeSMTP] = []

        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.login_args: tuple[str, str] | None = None
            self.message = None
            FakeSMTP.instances.append(self)

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def starttls(self, *, context) -> None:
            self.started_tls = context is not None

        def login(self, username: str, password: str) -> None:
            self.login_args = (username, password)

        def send_message(self, msg) -> None:
            self.message = msg

    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)

    provider = email_mod.SmtpEmailProvider(
        host="smtp.protonmail.ch",
        port=587,
        username="qtw@quip.network",
        password="token",
        sender="Quip Network <qtw@quip.network>",
        timeout_s=7.0,
    )
    provider.send(
        to="player@example.com",
        subject="Portfolio update",
        html="<p>Hello</p>",
        text="Hello",
    )

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.protonmail.ch", 587, 7.0)
    assert smtp.started_tls is True
    assert smtp.login_args == ("qtw@quip.network", "token")
    assert smtp.message["From"] == "Quip Network <qtw@quip.network>"
    assert smtp.message["To"] == "player@example.com"
    assert smtp.message["Subject"] == "Portfolio update"
    assert smtp.message.is_multipart()


def test_smtp_provider_rejects_header_line_breaks(monkeypatch):
    class FakeSMTP:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("SMTP should not be opened for unsafe headers")

    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)

    provider = email_mod.SmtpEmailProvider(
        host="smtp.protonmail.ch",
        port=587,
        username="qtw@quip.network",
        password="token",
        sender="Quip Network <qtw@quip.network>",
    )
    with pytest.raises(ValueError, match="subject"):
        provider.send(
            to="player@example.com",
            subject="Hello\r\nBcc: bad@example.com",
            html="<p>Hello</p>",
            text="Hello",
        )
