"""Portfolio-result email notifications.

Attendees opt in at sign-up (AgentConfig.update_frequency = 'daily' | 'hourly')
to receive a simple email with their agent's name + current performance.

The active provider (Resend over HTTPS) is registered at FastAPI startup. With no
RESEND_API_KEY present, NoopEmailProvider logs only and keeps local/tests
side-effect-free.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING, Protocol

import httpx

if TYPE_CHECKING:
    from .seeoff import SeeoffInsights

logger = logging.getLogger(__name__)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...


class NoopEmailProvider:
    """Default provider — logs instead of sending. Swap in a real one to go live."""

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info("email (noop) skipped; recipient and subject suppressed")


class ResendEmailProvider:
    """Transactional email via Resend's HTTPS API (api.resend.com, port 443).

    DigitalOcean blocks outbound SMTP, so this HTTPS path is the reliable sender
    on the droplet. Synchronous to match the EmailProvider contract — the caller
    already runs send() off the request path as a background task.
    """

    _ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, *, api_key: str, sender: str, timeout_s: float = 10.0) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout_s = timeout_s

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        response = httpx.post(
            self._ENDPOINT,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "from": _safe_header(self._sender, "from"),
                "to": [_safe_header(to, "to")],
                "subject": _safe_header(subject, "subject"),
                "html": html,
                "text": text,
            },
            timeout=self._timeout_s,
        )
        response.raise_for_status()


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


# Quip brand styling for the email masthead. The wordmark is the official hosted
# lockup PNG so the brand typography is pixel-correct in every client (custom web
# fonts are stripped by Gmail/most webmail). The brand fonts in the stack below
# only render where the client allows them (e.g. Apple Mail with the faces installed).
_DISPLAY_FONT = "'ABC Gaisyr',Georgia,'Times New Roman',serif"
_BODY_FONT = "-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif"
_MONO_FONT = "'ABC Favorit Mono',ui-monospace,SFMono-Regular,Menlo,monospace"
_LOGO_URL = "https://quip.network/images/brand/quip-network-lockup-horizontal-standard-on-light.png"


def _branded_html(inner: str) -> str:
    """Wrap body HTML in the Quip masthead: icon + wordmark + accent rule, on white."""
    return (
        '<div style="margin:0;padding:0;background:#FFFFFF">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#FFFFFF"><tr><td align="center" style="padding:36px 16px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px">'
        '<tr><td style="padding:0 6px">'
        f'<img src="{_LOGO_URL}" width="220" height="32" alt="Quip Network" '
        'style="display:block;border:0"></td></tr>'
        '<tr><td style="padding:16px 6px 0">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td style="height:3px;background:#4CE0FF;font-size:0;line-height:0">&nbsp;</td>'
        '<td style="height:3px;background:#A5C3D4;font-size:0;line-height:0">&nbsp;</td>'
        '<td style="height:3px;background:#FF92D5;font-size:0;line-height:0">&nbsp;</td>'
        "</tr></table></td></tr>"
        f'<tr><td style="padding:24px 6px 0;font-family:{_BODY_FONT};color:#1A1A1A;'
        f'font-size:16px;line-height:1.55">{inner}</td></tr>'
        "</table></td></tr></table></div>"
    )


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
        f"Your Quip Network trading agent at Quantum.Tech World is now worth "
        f"${total:,.0f} ({sign}${pl_abs:,.0f}, {sign}{abs(pl_pct):.2f}%).\n\n"
        f"Track it live and retune anytime from your profile.\n\n"
        f"— Quip Network"
    )
    inner = (
        f'<p style="margin:0 0 16px">Hi {html_name},</p>'
        '<p style="margin:0 0 8px">Your <strong>Quip Network</strong> trading agent at '
        "Quantum.Tech World is now worth "
        f'<span style="font-family:{_MONO_FONT};font-weight:600">${total:,.0f}</span> '
        f'<span style="color:{color};font-family:{_MONO_FONT}">({sign}${pl_abs:,.0f} · '
        f"{sign}{abs(pl_pct):.2f}%)</span>.</p>"
        '<p style="margin:16px 0 0">Track it live and retune anytime from your profile.</p>'
        f'<p style="margin:26px 0 0;color:#A9A9A9;font-size:13px;font-family:{_MONO_FONT}">'
        "— Quip Network</p>"
    )
    return PortfolioEmail(subject=subject, html=_branded_html(inner), text=text)


def render_seeoff_email(insights: SeeoffInsights) -> PortfolioEmail:
    """Personalised booth send-off: final P&L, leaderboard percentile, peak, solves, QPU win-rate."""
    display_name = _clean_display(insights.name) or "there"
    html_name = escape(display_name)
    pl = insights.final_pl_usd
    pct = insights.final_pl_pct
    sign = "+" if pl >= 0 else "−"
    color = "#0A832E" if pl >= 0 else "#FF6C78"
    subject = _safe_header(
        f"{display_name}: your quantum agent finished top {insights.top_percent}% "
        f"({sign}{abs(pct):.2f}%)",
        "subject",
    )
    text = (
        f"Hi {display_name},\n\n"
        "Thanks for optimizing a portfolio on a real quantum computer at Quantum.Tech World. "
        "Here's how your agent finished:\n\n"
        f"  Final P&L:     {sign}${abs(pl):,.0f} ({sign}{abs(pct):.2f}%)\n"
        f"  Leaderboard:   #{insights.rank} of {insights.total_agents} — top {insights.top_percent}%\n"
        f"  Peak:          +{insights.peak_pct:.2f}% (low {insights.trough_pct:+.2f}%)\n"
        f"  Optimizations: {insights.jobs_solved}, {insights.qpu_win_pct}% won by the quantum computer\n\n"
        "We hope you had fun playing and see you again at a future event. If you have any feedback, please let us know!\n\n"
        "— Quip Network"
    )
    row = (
        '<tr><td style="color:#71717B;padding-right:18px;white-space:nowrap">{k}</td>'
        '<td>{v}</td></tr>'
    )
    inner = (
        f'<p style="margin:0 0 16px">Hi {html_name},</p>'
        '<p style="margin:0 0 14px">Thanks for optimizing a portfolio on a real quantum computer at '
        "<strong>Quantum.Tech World</strong>. Here's how your agent finished:</p>"
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="font-family:{_MONO_FONT};font-size:15px;line-height:1.9">'
        + row.format(
            k="Final P&amp;L",
            v=f'<span style="color:{color};font-weight:600">{sign}${abs(pl):,.0f} · '
            f"{sign}{abs(pct):.2f}%</span>",
        )
        + row.format(
            k="Leaderboard",
            v=f"#{insights.rank} of {insights.total_agents} — "
            f"<strong>top {insights.top_percent}%</strong>",
        )
        + row.format(
            k="Peak",
            v=f'+{insights.peak_pct:.2f}% <span style="color:#A1A1AA">'
            f"(low {insights.trough_pct:+.2f}%)</span>",
        )
        + row.format(
            k="Optimizations",
            v=f"{insights.jobs_solved}, <strong>{insights.qpu_win_pct}% won by the "
            "quantum computer</strong>",
        )
        + "</table>"
        '<p style="margin:18px 0 0">We hope you had fun playing and see you again at a future '
        "event. If you have any feedback, please let us know!</p>"
        f'<p style="margin:26px 0 0;color:#A9A9A9;font-size:13px;font-family:{_MONO_FONT}">'
        "— Quip Network</p>"
    )
    return PortfolioEmail(subject=subject, html=_branded_html(inner), text=text)


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
        else '<p style="margin:0;color:#525252;font-size:14px">This is a one-time link to '
        "your agent — we won't email you again.</p>"
    )
    text = (
        f"Hi {display_name},\n\n"
        "Your Quip Network trading agent at Quantum.Tech World is live. Your "
        "$10,000 starting portfolio has been created and will update as the "
        "booth game runs.\n\n"
        f"Follow and retune your agent here:\n{safe_link}\n\n"
        f"{text_closing}"
        "— Quip Network"
    )
    inner = (
        f'<p style="font-family:{_DISPLAY_FONT};font-size:25px;line-height:1.18;'
        f'margin:6px 0 18px;color:#1A1A1A">Your agent is live, {html_name}.</p>'
        '<p style="margin:0 0 16px">Your <strong>Quip Network</strong> trading agent at '
        "Quantum.Tech World is live. Your starting portfolio of "
        f'<span style="font-family:{_MONO_FONT};font-weight:600">$10,000</span> has been '
        "created and will update as the booth game runs.</p>"
        f'<p style="margin:26px 0"><a href="{href}" style="display:inline-block;'
        "padding:12px 26px;background:#FFFFFF;color:#1A1A1A;border:1.5px solid #1A1A1A;"
        f"border-radius:10px;text-decoration:none;font-family:{_BODY_FONT};font-weight:600;"
        'font-size:15px">Open my agent</a></p>'
        f"{html_closing}"
        f'<p style="margin:26px 0 0;color:#A9A9A9;font-size:13px;font-family:{_MONO_FONT}">'
        "— Quip Network</p>"
    )
    return PortfolioEmail(subject=subject, html=_branded_html(inner), text=text)


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
