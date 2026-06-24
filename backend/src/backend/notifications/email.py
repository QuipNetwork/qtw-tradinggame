"""Portfolio-result email notifications.

Attendees opt in at sign-up (AgentConfig.update_frequency = 'daily' | 'hourly')
to receive a simple email with their agent's name + current performance.

The active provider is registered at FastAPI startup. With no SMTP env present,
NoopEmailProvider logs only and keeps local/tests side-effect-free.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from typing import Protocol

logger = logging.getLogger(__name__)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...


class NoopEmailProvider:
    """Default provider — logs instead of sending. Swap in a real one to go live."""

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info("email (noop) skipped; recipient and subject suppressed")


class SmtpEmailProvider:
    """TLS SMTP provider for Proton or another SMTP relay."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        timeout_s: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout_s = timeout_s

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = _safe_header(subject, "subject")
        msg["From"] = _safe_header(self._sender, "from")
        msg["To"] = _safe_header(to, "to")
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        context = ssl.create_default_context()
        if self._port == 465:
            with smtplib.SMTP_SSL(
                self._host,
                self._port,
                timeout=self._timeout_s,
                context=context,
            ) as server:
                server.login(self._username, self._password)
                server.send_message(msg)
            return

        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_s) as server:
            server.starttls(context=context)
            server.login(self._username, self._password)
            server.send_message(msg)


_provider: EmailProvider = NoopEmailProvider()


def set_email_provider(provider: EmailProvider) -> None:
    """Register the active email provider (call once at startup)."""
    global _provider
    _provider = provider


def get_email_provider() -> EmailProvider:
    return _provider


@dataclass(frozen=True)
class PortfolioEmail:
    subject: str
    html: str
    text: str


def _clean_display(value: str) -> str:
    return " ".join(_CONTROL_RE.sub(" ", value).split()).strip()


def _safe_header(value: str, field: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field} header contains a line break")
    cleaned = _clean_display(value)
    if not cleaned:
        raise ValueError(f"{field} header is blank")
    return cleaned


def render_portfolio_email(
    *, name: str, total: float, pl_usd: float, pl_pct: float
) -> PortfolioEmail:
    """Simple templated email: player name + current portfolio performance."""
    display_name = _clean_display(name) or "there"
    html_name = escape(display_name)
    sign = "+" if pl_usd >= 0 else "−"
    pl_abs = abs(pl_usd)
    color = "#0A832E" if pl_usd >= 0 else "#FF6C78"
    subject = _safe_header(
        f"{display_name}: your agent is {sign}${pl_abs:,.0f} ({sign}{abs(pl_pct):.2f}%)",
        "subject",
    )
    text = (
        f"Hi {display_name},\n\n"
        f"Your Quantum.Tech World trading agent is now worth ${total:,.0f} "
        f"({sign}${pl_abs:,.0f}, {sign}{abs(pl_pct):.2f}%).\n\n"
        f"Track it live and retune anytime from your profile.\n\n"
        f"— Quip Network"
    )
    html = (
        '<div style="font-family:Inter,Arial,sans-serif;color:#18181b">'
        f"<p>Hi {html_name},</p>"
        "<p>Your <strong>Quantum.Tech World</strong> trading agent is now worth "
        f"<strong>${total:,.0f}</strong> "
        f'<span style="color:{color}">({sign}${pl_abs:,.0f} · '
        f"{sign}{abs(pl_pct):.2f}%)</span>.</p>"
        "<p>Track it live and retune anytime from your profile.</p>"
        '<p style="color:#71717b">— Quip Network</p>'
        "</div>"
    )
    return PortfolioEmail(subject=subject, html=html, text=text)


def render_signup_email(*, name: str, link: str, updates_opt_in: bool = False) -> PortfolioEmail:
    """Signup confirmation carrying the attendee's secure agent link.

    Sent to anyone who gives an email (the link is their way back to the agent).
    When they did not opt into result emails, a closing line states the one-time,
    no-further-mail intent.
    """
    display_name = _clean_display(name) or "there"
    html_name = escape(display_name)
    safe_link = _safe_header(link, "link")
    href = escape(safe_link, quote=True)
    subject = _safe_header(f"{display_name}, your Quip Network agent is live", "subject")
    text_closing = (
        ""
        if updates_opt_in
        else "This is a one-time link to your agent — we won't email you again.\n\n"
    )
    html_closing = (
        ""
        if updates_opt_in
        else '<p style="color:#71717b">This is a one-time link to your agent — '
        "we won't email you again.</p>"
    )
    text = (
        f"Hi {display_name},\n\n"
        "Your Quantum.Tech World trading agent is live. Your $10,000 starting "
        "portfolio has been created and will update as the booth game runs.\n\n"
        f"Follow and retune your agent here:\n{safe_link}\n\n"
        f"{text_closing}"
        "— Quip Network"
    )
    html = (
        '<div style="font-family:Inter,Arial,sans-serif;color:#18181b">'
        f"<p>Hi {html_name},</p>"
        "<p>Your <strong>Quantum.Tech World</strong> trading agent is live. "
        "Your <strong>$10,000</strong> starting portfolio has been created and "
        "will update as the booth game runs.</p>"
        f'<p><a href="{href}" style="display:inline-block;padding:10px 18px;'
        'background:#18181b;color:#ffffff;border-radius:8px;text-decoration:none">'
        "Open my agent</a></p>"
        f"{html_closing}"
        '<p style="color:#71717b">— Quip Network</p>'
        "</div>"
    )
    return PortfolioEmail(subject=subject, html=html, text=text)


def send_signup_confirmation(
    *, to: str, name: str, link: str, updates_opt_in: bool = False
) -> None:
    """Render + dispatch the initial signup confirmation with the agent link."""
    email = render_signup_email(name=name, link=link, updates_opt_in=updates_opt_in)
    get_email_provider().send(to=to, subject=email.subject, html=email.html, text=email.text)


def send_portfolio_update(
    *, to: str, name: str, total: float, pl_usd: float, pl_pct: float
) -> None:
    """Render + dispatch one portfolio-result email via the active provider."""
    email = render_portfolio_email(name=name, total=total, pl_usd=pl_usd, pl_pct=pl_pct)
    get_email_provider().send(to=to, subject=email.subject, html=email.html, text=email.text)
