"""Agent store — config + holdings + valuation + retune history.

The base store is a process-local dict guarded by a lock. `DATABASE_URL` swaps
the process singleton to a SQL-backed subclass while keeping this in-memory path
for tests, offline runs, and local development. Holdings are stored as token
units so mark-to-market is just units times spot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

from ..api.schemas import AgentConfig, AgentUpdate, SliderValues, ValuationHistoryPoint
from ..financial.slider_map import rebalance_every_hours

VALUATION_HISTORY_MAX_POINTS = 240


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _next_rebalance_at(
    sliders: SliderValues, solved_at: datetime
) -> tuple[str, str | None, float | None]:
    interval_hours = rebalance_every_hours(sliders.rebalance_frequency)
    if interval_hours is None:
        return solved_at.isoformat(), None, None
    next_at = solved_at + timedelta(hours=interval_hours)
    return solved_at.isoformat(), next_at.isoformat(), interval_hours


@dataclass
class AgentRecord:
    id: str
    name: str
    handle: str | None
    email: str | None
    reach_out: list[str] | None
    updates_opt_in: bool | None
    sliders: SliderValues
    assets: list[str] | None  # the player's basket (re-selectable on retune)
    bankroll: float
    holdings_units: dict[str, float] = field(default_factory=dict)
    total: float = 0.0  # current mark-to-market value
    pl_usd: float = 0.0
    pl_pct: float = 0.0
    jobs_solved: int = 0
    primary_provider: str = "CPU"  # ProviderType of the latest winning solve
    created_at: str = ""
    last_solved_at: str | None = None
    next_rebalance_at: str | None = None
    rebalance_interval_hours: float | None = None
    valuation_as_of: str | None = None
    valuation_stale: bool = False
    update_frequency: str | None = None  # 'daily' | 'hourly' email cadence (opt-in)
    last_update_email_at: str | None = None  # ISO-8601 UTC of the last result email (throttle)
    token_hash: str | None = None  # sha256 of the agent's capability token (owner auth)

    def to_config(self) -> AgentConfig:
        return AgentConfig(
            name=self.name,
            handle=self.handle,
            email=self.email,
            reach_out=self.reach_out,
            updates_opt_in=self.updates_opt_in,
            update_frequency=self.update_frequency,
            sliders=self.sliders,
            assets=self.assets,
            last_solved_at=self.last_solved_at,
            next_rebalance_at=self.next_rebalance_at,
            rebalance_interval_hours=self.rebalance_interval_hours,
        )


class AgentStore:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}
        self._valuation_history: dict[str, list[ValuationHistoryPoint]] = {}
        self._lock = RLock()

    def create(
        self, config: AgentConfig, bankroll: float, *, token_hash: str | None = None
    ) -> AgentRecord:
        with self._lock:
            agent_id = uuid4().hex[:8]
            created = _now_iso()
            record = AgentRecord(
                id=agent_id,
                name=config.name,
                handle=config.handle,
                email=config.email,
                reach_out=config.reach_out,
                updates_opt_in=config.updates_opt_in,
                update_frequency=config.update_frequency,
                sliders=config.sliders,
                assets=list(config.assets) if config.assets else None,
                bankroll=bankroll,
                total=bankroll,
                created_at=created,
                # Seed the throttle to creation time so the first result email waits a
                # full opt-in window instead of arriving right behind the signup email.
                last_update_email_at=created,
                token_hash=token_hash,
            )
            self._agents[agent_id] = record
            return record

    def get(self, agent_id: str) -> AgentRecord | None:
        with self._lock:
            return self._agents.get(agent_id)

    def all(self) -> list[AgentRecord]:
        with self._lock:
            return list(self._agents.values())

    def update_sliders(self, agent_id: str, sliders: SliderValues) -> None:
        with self._lock:
            record = self._agents[agent_id]
            record.sliders = sliders

    def update_assets(self, agent_id: str, assets: list[str]) -> None:
        with self._lock:
            record = self._agents[agent_id]
            record.assets = list(assets)

    def apply_solve(
        self,
        agent_id: str,
        holdings_units: dict[str, float],
        total: float,
        provider_type: str,
    ) -> None:
        """Record the outcome of a solve: new holdings, valuation, provider, count."""
        with self._lock:
            record = self._agents[agent_id]
            solved_at, next_at, interval_hours = _next_rebalance_at(
                record.sliders, datetime.now(UTC)
            )
            record.holdings_units = dict(holdings_units)
            record.total = total
            record.pl_usd = total - record.bankroll
            record.pl_pct = (record.pl_usd / record.bankroll * 100.0) if record.bankroll else 0.0
            record.jobs_solved += 1
            record.primary_provider = provider_type
            record.last_solved_at = solved_at
            record.next_rebalance_at = next_at
            record.rebalance_interval_hours = interval_hours
            record.valuation_as_of = solved_at
            record.valuation_stale = False

    def ensure_rebalance_schedule(self, agent_id: str) -> None:
        """Initialize missing rebalance timestamps for a hydrated active agent."""
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None or not record.holdings_units or record.next_rebalance_at:
                return
            solved_at, next_at, interval_hours = _next_rebalance_at(
                record.sliders, datetime.now(UTC)
            )
            record.last_solved_at = solved_at
            record.next_rebalance_at = next_at
            record.rebalance_interval_hours = interval_hours

    def defer_rebalance(self, agent_id: str, next_rebalance_at: str) -> None:
        """Move the next scheduled rebalance to a later timestamp."""
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return
            record.next_rebalance_at = next_rebalance_at

    def mark_update_email_sent(self, agent_id: str, ts: str) -> None:
        """Record when the last throttled result email went out."""
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return
            record.last_update_email_at = ts

    def set_valuation(self, agent_id: str, update: AgentUpdate) -> None:
        """Update the mark-to-market valuation from the MTM loop."""
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return
            record.total = update.total
            record.pl_usd = update.pl_usd
            record.pl_pct = update.pl_pct
            record.valuation_as_of = update.as_of
            record.valuation_stale = update.stale

    def record_valuation_snapshot(self, agent_id: str, update: AgentUpdate) -> None:
        """Sink sampled valuation history for charting and later analytics."""
        with self._lock:
            if agent_id not in self._agents:
                return
            history = self._valuation_history.setdefault(agent_id, [])
            history.append(_point_from_update(update))
            del history[:-VALUATION_HISTORY_MAX_POINTS]

    def valuation_history(self, agent_id: str, limit: int = 60) -> list[ValuationHistoryPoint]:
        """Return sampled valuation history plus the latest in-memory MTM value."""
        limit = _bounded_history_limit(limit)
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return []
            points = list(self._valuation_history.get(agent_id, []))[-limit:]
            return _with_current_point(points, _point_from_record(record))[-limit:]

    def reset(self) -> None:
        with self._lock:
            self._agents.clear()
            self._valuation_history.clear()


_store: AgentStore | None = None


def get_agent_store() -> AgentStore:
    """Return the process-wide agent store singleton."""
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def set_agent_store(store: AgentStore | None) -> None:
    """Override the process-wide store for tests; None rebuilds from config."""
    global _store
    _store = store


def _build_store() -> AgentStore:
    from .. import config

    if config.DATABASE_URL:
        from .db import DbAgentStore

        return DbAgentStore(config.DATABASE_URL, environment=config.APP_ENV)
    return AgentStore()


def _bounded_history_limit(limit: int) -> int:
    return max(1, min(int(limit), VALUATION_HISTORY_MAX_POINTS))


def _point_from_update(update: AgentUpdate) -> ValuationHistoryPoint:
    return ValuationHistoryPoint(
        total=update.total,
        pl_usd=update.pl_usd,
        pl_pct=update.pl_pct,
        as_of=update.as_of,
        stale=update.stale,
    )


def _point_from_record(record: AgentRecord) -> ValuationHistoryPoint:
    return ValuationHistoryPoint(
        total=record.total,
        pl_usd=record.pl_usd,
        pl_pct=record.pl_pct,
        as_of=record.valuation_as_of or record.last_solved_at or record.created_at or _now_iso(),
        stale=record.valuation_stale,
    )


def _with_current_point(
    points: list[ValuationHistoryPoint], current: ValuationHistoryPoint
) -> list[ValuationHistoryPoint]:
    if not points:
        return [current]
    last = points[-1]
    same_value = (
        abs(last.total - current.total) < 0.005
        and abs(last.pl_usd - current.pl_usd) < 0.005
        and abs(last.pl_pct - current.pl_pct) < 0.0005
    )
    if same_value and last.as_of == current.as_of and last.stale == current.stale:
        return points
    return [*points, current]
