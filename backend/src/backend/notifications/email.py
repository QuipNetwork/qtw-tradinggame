"""Portfolio-result email notifications — provider-agnostic scaffold.

Attendees opt in at sign-up (AgentConfig.update_frequency = 'daily' | 'hourly')
to receive a simple email with their agent's name + current performance.

This module is deliberately decoupled from any email vendor. To go live:
  1. Implement EmailProvider for the chosen service (Resend / Postmark / SES /
     SMTP) and register it via set_email_provider() at startup.
  2. Verify a sending domain (SPF/DKIM on a quip.network subdomain) or mail
     lands in spam.
  3. Wire send_portfolio_update() into orchestration/scheduler.py so each
     opted-in agent is emailed on its cadence (hourly/daily) using the latest
     mark-to-market figures.

Until a real provider is registered, NoopEmailProvider only logs — nothing is
sent, so importing/using this module is side-effect-free.

Example provider (Resend) for when the service is chosen:

    import httpx
    class ResendProvider:
        def __init__(self, api_key: str, sender: str) -> None:
            self._key, self._sender = api_key, sender
        def send(self, *, to, subject, html, text) -> None:
            httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._key}"},
                json={"from": self._sender, "to": to, "subject": subject,
                      "html": html, "text": text},
                timeout=10,
            ).raise_for_status()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...


class NoopEmailProvider:
    """Default provider — logs instead of sending. Swap in a real one to go live."""

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info("email (noop) to=%s subject=%r", to, subject)


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


def render_portfolio_email(
    *, name: str, total: float, pl_usd: float, pl_pct: float
) -> PortfolioEmail:
    """Simple templated email: player name + current portfolio performance."""
    sign = "+" if pl_usd >= 0 else "−"
    pl_abs = abs(pl_usd)
    color = "#0A832E" if pl_usd >= 0 else "#FF6C78"
    subject = f"{name}: your agent is {sign}${pl_abs:,.0f} ({sign}{abs(pl_pct):.2f}%)"
    text = (
        f"Hi {name},\n\n"
        f"Your Quantum.Tech World trading agent is now worth ${total:,.0f} "
        f"({sign}${pl_abs:,.0f}, {sign}{abs(pl_pct):.2f}%).\n\n"
        f"Track it live and retune anytime from your profile.\n\n"
        f"— Quip Network"
    )
    html = (
        '<div style="font-family:Inter,Arial,sans-serif;color:#18181b">'
        f"<p>Hi {name},</p>"
        "<p>Your <strong>Quantum.Tech World</strong> trading agent is now worth "
        f'<strong>${total:,.0f}</strong> '
        f'<span style="color:{color}">({sign}${pl_abs:,.0f} · '
        f"{sign}{abs(pl_pct):.2f}%)</span>.</p>"
        "<p>Track it live and retune anytime from your profile.</p>"
        '<p style="color:#71717b">— Quip Network</p>'
        "</div>"
    )
    return PortfolioEmail(subject=subject, html=html, text=text)


def send_portfolio_update(
    *, to: str, name: str, total: float, pl_usd: float, pl_pct: float
) -> None:
    """Render + dispatch one portfolio-result email via the active provider."""
    email = render_portfolio_email(name=name, total=total, pl_usd=pl_usd, pl_pct=pl_pct)
    get_email_provider().send(
        to=to, subject=email.subject, html=email.html, text=email.text
    )
