"""Per-agent QPU admission budget.

The budget limits attempts that would include D-Wave in the solver race. It is
checked before race dispatch, so a rejected request does not touch the QPU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Literal

from .. import config
from ..api.schemas import QpuBudgetStatus

QpuBudgetSource = Literal["manual", "scheduled"]


@dataclass(frozen=True)
class QpuBudgetEvent:
    agent_id: str
    source: QpuBudgetSource
    reserved_at: datetime


class QpuBudgetExceeded(Exception):
    """Raised when an agent has no QPU admissions left in the rolling window."""

    def __init__(self, status: QpuBudgetStatus) -> None:
        self.status = status
        retry = status.retry_after_seconds
        super().__init__(f"QPU solve limit reached; try again in {retry} seconds")


class QpuBudgetStore:
    def __init__(self) -> None:
        self._events: list[QpuBudgetEvent] = []
        self._lock = RLock()

    def reserve(
        self,
        agent_id: str,
        *,
        source: QpuBudgetSource,
        now: datetime | None = None,
    ) -> QpuBudgetStatus:
        """Atomically reserve one QPU admission or raise QpuBudgetExceeded."""
        now = _coerce_utc(now)
        with self._lock:
            self._prune_locked(now)
            status = self.status(agent_id, now=now)
            if status.used >= status.limit:
                raise QpuBudgetExceeded(status)
            self._events.append(QpuBudgetEvent(agent_id, source, now))
            return self.status(agent_id, now=now)

    def status(self, agent_id: str, *, now: datetime | None = None) -> QpuBudgetStatus:
        now = _coerce_utc(now)
        with self._lock:
            self._prune_locked(now)
            times = sorted(
                event.reserved_at for event in self._events if event.agent_id == agent_id
            )
        return _status_from_times(times, now=now)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _prune_locked(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=config.QPU_BUDGET_WINDOW_S)
        self._events = [event for event in self._events if event.reserved_at > cutoff]


_store: QpuBudgetStore | None = None


def get_qpu_budget_store() -> QpuBudgetStore:
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def set_qpu_budget_store(store: QpuBudgetStore | None) -> None:
    global _store
    _store = store


def _build_store() -> QpuBudgetStore:
    if config.DATABASE_URL:
        from .db import DbQpuBudgetStore

        return DbQpuBudgetStore(config.DATABASE_URL, environment=config.APP_ENV)
    return QpuBudgetStore()


def _status_from_times(times: list[datetime], *, now: datetime) -> QpuBudgetStatus:
    limit = config.QPU_BUDGET_MAX_ATTEMPTS
    window_s = config.QPU_BUDGET_WINDOW_S
    cutoff = now - timedelta(seconds=window_s)
    active = sorted(t for t in times if t > cutoff)
    retry_after = 0
    next_available_at: str | None = None
    if len(active) >= limit and active:
        next_at = active[0] + timedelta(seconds=window_s)
        retry_after = max(0, math.ceil((next_at - now).total_seconds()))
        next_available_at = next_at.isoformat()
    return QpuBudgetStatus(
        used=len(active),
        limit=limit,
        windowSeconds=window_s,
        retryAfterSeconds=retry_after,
        nextAvailableAt=next_available_at,
    )


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
