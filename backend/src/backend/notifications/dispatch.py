"""Throttled result-email dispatch.

After a rebalance, send at most one portfolio-result email per opt-in window
(1h for 'hourly', 24h otherwise). Pure orchestration over the agent store + the
render/send primitives in `email.py`, so `email.py` stays dependency-light.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from ..persistence.agents import AgentRecord, AgentStore
from .email import send_portfolio_update

logger = logging.getLogger(__name__)

_HOURLY = timedelta(hours=1)
_DEFAULT_WINDOW = timedelta(hours=24)  # 'daily' or unset


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _email_due(record: AgentRecord, now: datetime) -> bool:
    last = _parse_iso(record.last_update_email_at)
    if last is None:
        return True
    window = _HOURLY if (record.update_frequency or "").lower() == "hourly" else _DEFAULT_WINDOW
    return now - last >= window


def maybe_send_update_email(record: AgentRecord, *, now: datetime, store: AgentStore) -> None:
    """Send a throttled portfolio-result email after a solve; never raise."""
    if not record.email or record.updates_opt_in is not True:
        return
    if not _email_due(record, now):
        return
    try:
        send_portfolio_update(
            to=record.email,
            name=record.name,
            total=record.total,
            pl_usd=record.pl_usd,
            pl_pct=record.pl_pct,
        )
        store.mark_update_email_sent(record.id, now.isoformat())
    except Exception:
        logger.warning("result email failed agent_id=%s", record.id, exc_info=True)
