"""SQL-backed persistence stores.

`DATABASE_URL` enables these stores for Supabase/Postgres deployment. Tests can
instantiate them against SQLite, while the default app path stays in-memory when
the env var is unset.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .. import config
from ..api.schemas import AgentConfig, AgentUpdate, SliderValues, ValuationHistoryPoint
from .agents import (
    AgentRecord,
    AgentStore,
    _bounded_history_limit,
    _point_from_record,
    _with_current_point,
)
from .jobs import JobRecord, JobStore
from .qpu_budget import (
    QpuBudgetExceeded,
    QpuBudgetSource,
    QpuBudgetStatus,
    QpuBudgetStore,
    _coerce_utc,
    _status_from_times,
)

metadata = MetaData()

agents_table = Table(
    "agents",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String, nullable=False),
    Column("handle", String, nullable=True),
    Column("email", String, nullable=True),
    Column("reach_out", JSON, nullable=True),
    Column("updates_opt_in", Boolean, nullable=True),
    Column("update_frequency", String(16), nullable=True),
    Column("sliders", JSON, nullable=False),
    Column("assets", JSON, nullable=True),
    Column("bankroll", Float, nullable=False),
    Column("total", Float, nullable=False),
    Column("pl_usd", Float, nullable=False),
    Column("pl_pct", Float, nullable=False),
    Column("jobs_solved", Integer, nullable=False),
    Column("primary_provider", String(8), nullable=False),
    Column("last_solved_at", String, nullable=True),
    Column("next_rebalance_at", String, nullable=True),
    Column("rebalance_interval_hours", Float, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("environment", String, nullable=False),
)

agent_holdings_table = Table(
    "agent_holdings",
    metadata,
    Column("agent_id", String(32), ForeignKey("agents.id"), primary_key=True),
    Column("ticker", String(16), primary_key=True),
    Column("units", Float, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("environment", String, nullable=False),
)

jobs_table = Table(
    "jobs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("agent_id", String(32), ForeignKey("agents.id"), nullable=False),
    Column("q_hash", String(64), nullable=False),
    Column("provider", String(32), nullable=False),
    Column("provider_role", String(8), nullable=False),
    Column("solve_time_s", Float, nullable=False),
    Column("deadline_s", Float, nullable=False),
    Column("feasible", Boolean, nullable=False),
    Column("solved_at", String, nullable=False),
    Column("environment", String, nullable=False),
)

solve_snapshots_table = Table(
    "solve_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_id", String(32), ForeignKey("jobs.id"), nullable=False),
    Column("agent_id", String(32), ForeignKey("agents.id"), nullable=False),
    Column("sliders", JSON, nullable=False),
    Column("assets", JSON, nullable=False),
    Column("portfolio", JSON, nullable=False),
    Column("holdings_units", JSON, nullable=False),
    Column("solver_results", JSON, nullable=False),
    Column("winner_provider", String(32), nullable=False),
    Column("created_at", String, nullable=False),
    Column("environment", String, nullable=False),
)

valuation_snapshots_table = Table(
    "valuation_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String(32), ForeignKey("agents.id"), nullable=False),
    Column("total", Float, nullable=False),
    Column("pl_usd", Float, nullable=False),
    Column("pl_pct", Float, nullable=False),
    Column("holdings", JSON, nullable=False),
    Column("as_of", String, nullable=True),
    Column("stale", Boolean, nullable=False),
    Column("created_at", String, nullable=False),
    Column("environment", String, nullable=False),
)

qpu_budget_events_table = Table(
    "qpu_budget_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String(32), ForeignKey("agents.id"), nullable=False),
    Column("source", String(16), nullable=False),
    Column("reserved_at", String, nullable=False),
    Column("environment", String, nullable=False),
)


def create_db_engine(database_url: str) -> Engine:
    url = _normalize_database_url(database_url)
    # Hosted Postgres (Supabase): pre-ping + recycle so a connection the pooler
    # closed while idle never surfaces as a 500; a bounded pool to stay under the
    # project's connection limit (one per store); TLS required. SQLite (tests)
    # keeps the plain engine — these QueuePool kwargs don't apply to it.
    if url.startswith("postgresql"):
        return create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=3,
            max_overflow=2,
            connect_args={"sslmode": "require"},
        )
    return create_engine(url, future=True)


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_columns(engine: Engine, table_name: str, columns: dict[str, str]) -> None:
    existing = {column["name"] for column in inspect(engine).get_columns(table_name)}
    missing = [(name, ddl) for name, ddl in columns.items() if name not in existing]
    if not missing:
        return
    with engine.begin() as conn:
        for name, ddl in missing:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}"))


def _ensure_rebalance_interval_type(engine: Engine) -> None:
    """Postgres needs an explicit INTEGER→FLOAT migration for 30m cadences."""
    column = next(
        (
            column
            for column in inspect(engine).get_columns("agents")
            if column["name"] == "rebalance_interval_hours"
        ),
        None,
    )
    if column is None:
        return
    type_name = str(column["type"]).upper()
    if any(kind in type_name for kind in ("DOUBLE", "FLOAT", "REAL")):
        return
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE agents "
                    "ALTER COLUMN rebalance_interval_hours TYPE DOUBLE PRECISION "
                    "USING rebalance_interval_hours::double precision"
                )
            )


class DbAgentStore(AgentStore):
    """DB write-through store with the in-memory dict retained as the hot path."""

    def __init__(
        self,
        database_url: str,
        *,
        environment: str,
        allow_reset: bool = False,
    ) -> None:
        super().__init__()
        self._engine = create_db_engine(database_url)
        self._environment = environment
        self._allow_reset = allow_reset
        metadata.create_all(self._engine)
        _ensure_columns(
            self._engine,
            "agents",
            {
                "last_solved_at": "VARCHAR",
                "next_rebalance_at": "VARCHAR",
                "rebalance_interval_hours": "FLOAT",
                "update_frequency": "VARCHAR",
            },
        )
        _ensure_rebalance_interval_type(self._engine)
        self._load()

    @property
    def engine(self) -> Engine:
        return self._engine

    def create(self, config: AgentConfig, bankroll: float) -> AgentRecord:
        for _ in range(3):
            record = super().create(config, bankroll)
            try:
                with self._engine.begin() as conn:
                    conn.execute(insert(agents_table), self._agent_values(record))
                return record
            except IntegrityError:
                with self._lock:
                    self._agents.pop(record.id, None)  # id collision — retry with a fresh id
            except Exception:  # noqa: BLE001 — keep the hot path consistent on any DB failure
                # Any other DB failure (e.g. the database is down) must not leave the record in the
                # in-memory hot path unpersisted — write-through has to stay consistent. Surface it.
                with self._lock:
                    self._agents.pop(record.id, None)
                raise
        raise RuntimeError("could not allocate a unique agent id")

    def update_sliders(self, agent_id: str, sliders: SliderValues) -> None:
        super().update_sliders(agent_id, sliders)
        with self._engine.begin() as conn:
            conn.execute(
                update(agents_table)
                .where(agents_table.c.id == agent_id)
                .where(agents_table.c.environment == self._environment)
                .values(sliders=sliders.model_dump(by_alias=True), updated_at=_now_iso())
            )

    def update_assets(self, agent_id: str, assets: list[str]) -> None:
        super().update_assets(agent_id, assets)
        with self._engine.begin() as conn:
            conn.execute(
                update(agents_table)
                .where(agents_table.c.id == agent_id)
                .where(agents_table.c.environment == self._environment)
                .values(assets=list(assets), updated_at=_now_iso())
            )

    def apply_solve(
        self,
        agent_id: str,
        holdings_units: dict[str, float],
        total: float,
        provider_type: str,
    ) -> None:
        super().apply_solve(agent_id, holdings_units, total, provider_type)
        record = self.get(agent_id)
        if record is None:
            return

        now = _now_iso()
        with self._engine.begin() as conn:
            conn.execute(
                update(agents_table)
                .where(agents_table.c.id == agent_id)
                .where(agents_table.c.environment == self._environment)
                .values(
                    total=record.total,
                    pl_usd=record.pl_usd,
                    pl_pct=record.pl_pct,
                    jobs_solved=record.jobs_solved,
                    primary_provider=record.primary_provider,
                    last_solved_at=record.last_solved_at,
                    next_rebalance_at=record.next_rebalance_at,
                    rebalance_interval_hours=record.rebalance_interval_hours,
                    updated_at=now,
                )
            )
            conn.execute(
                delete(agent_holdings_table)
                .where(agent_holdings_table.c.agent_id == agent_id)
                .where(agent_holdings_table.c.environment == self._environment)
            )
            rows = [
                {
                    "agent_id": agent_id,
                    "ticker": ticker,
                    "units": units,
                    "updated_at": now,
                    "environment": self._environment,
                }
                for ticker, units in holdings_units.items()
            ]
            if rows:
                conn.execute(insert(agent_holdings_table), rows)

    def ensure_rebalance_schedule(self, agent_id: str) -> None:
        super().ensure_rebalance_schedule(agent_id)
        record = self.get(agent_id)
        if record is None:
            return
        with self._engine.begin() as conn:
            conn.execute(
                update(agents_table)
                .where(agents_table.c.id == agent_id)
                .where(agents_table.c.environment == self._environment)
                .values(
                    last_solved_at=record.last_solved_at,
                    next_rebalance_at=record.next_rebalance_at,
                    rebalance_interval_hours=record.rebalance_interval_hours,
                    updated_at=_now_iso(),
                )
            )

    def defer_rebalance(self, agent_id: str, next_rebalance_at: str) -> None:
        super().defer_rebalance(agent_id, next_rebalance_at)
        with self._engine.begin() as conn:
            conn.execute(
                update(agents_table)
                .where(agents_table.c.id == agent_id)
                .where(agents_table.c.environment == self._environment)
                .values(next_rebalance_at=next_rebalance_at, updated_at=_now_iso())
            )

    def record_valuation_snapshot(self, agent_id: str, update_: AgentUpdate) -> None:
        super().record_valuation_snapshot(agent_id, update_)
        with self._engine.begin() as conn:
            conn.execute(
                insert(valuation_snapshots_table),
                {
                    "agent_id": agent_id,
                    "total": update_.total,
                    "pl_usd": update_.pl_usd,
                    "pl_pct": update_.pl_pct,
                    "holdings": [h.model_dump() for h in update_.holdings],
                    "as_of": update_.as_of,
                    "stale": update_.stale,
                    "created_at": _now_iso(),
                    "environment": self._environment,
                },
            )

    def valuation_history(self, agent_id: str, limit: int = 60) -> list[ValuationHistoryPoint]:
        limit = _bounded_history_limit(limit)
        record = self.get(agent_id)
        if record is None:
            return []

        with self._engine.begin() as conn:
            rows = (
                conn.execute(
                    select(
                        valuation_snapshots_table.c.total,
                        valuation_snapshots_table.c.pl_usd,
                        valuation_snapshots_table.c.pl_pct,
                        valuation_snapshots_table.c.as_of,
                        valuation_snapshots_table.c.stale,
                    )
                    .where(valuation_snapshots_table.c.agent_id == agent_id)
                    .where(valuation_snapshots_table.c.environment == self._environment)
                    .order_by(valuation_snapshots_table.c.id.desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )

        points = [
            ValuationHistoryPoint(
                total=row["total"],
                pl_usd=row["pl_usd"],
                pl_pct=row["pl_pct"],
                as_of=row["as_of"],
                stale=row["stale"],
            )
            for row in reversed(rows)
        ]
        if points and record.valuation_as_of is None:
            return points[-limit:]
        return _with_current_point(points, _point_from_record(record))[-limit:]

    def reset(self) -> None:
        super().reset()
        if not self._allow_reset:
            return
        with self._engine.begin() as conn:
            for table in (
                valuation_snapshots_table,
                solve_snapshots_table,
                jobs_table,
                agent_holdings_table,
                agents_table,
            ):
                conn.execute(delete(table).where(table.c.environment == self._environment))

    def _load(self) -> None:
        with self._engine.begin() as conn:
            agent_rows = conn.execute(
                select(agents_table).where(agents_table.c.environment == self._environment)
            ).mappings()
            with self._lock:
                for row in agent_rows:
                    record = AgentRecord(
                        id=row["id"],
                        name=row["name"],
                        handle=row["handle"],
                        email=row["email"],
                        reach_out=list(row["reach_out"]) if row["reach_out"] else None,
                        updates_opt_in=row["updates_opt_in"],
                        update_frequency=row["update_frequency"],
                        sliders=SliderValues(**row["sliders"]),
                        assets=list(row["assets"]) if row["assets"] else None,
                        bankroll=row["bankroll"],
                        holdings_units={},
                        total=row["total"],
                        pl_usd=row["pl_usd"],
                        pl_pct=row["pl_pct"],
                        jobs_solved=row["jobs_solved"],
                        primary_provider=row["primary_provider"],
                        created_at=row["created_at"],
                        last_solved_at=row["last_solved_at"],
                        next_rebalance_at=row["next_rebalance_at"],
                        rebalance_interval_hours=row["rebalance_interval_hours"],
                    )
                    self._agents[record.id] = record

                holding_rows = conn.execute(
                    select(agent_holdings_table).where(
                        agent_holdings_table.c.environment == self._environment
                    )
                ).mappings()
                for row in holding_rows:
                    record = self._agents.get(row["agent_id"])
                    if record is not None:
                        record.holdings_units[row["ticker"]] = row["units"]

    def _agent_values(self, record: AgentRecord) -> dict[str, Any]:
        now = _now_iso()
        return {
            "id": record.id,
            "name": record.name,
            "handle": record.handle,
            "email": record.email,
            "reach_out": record.reach_out,
            "updates_opt_in": record.updates_opt_in,
            "update_frequency": record.update_frequency,
            "sliders": record.sliders.model_dump(by_alias=True),
            "assets": record.assets,
            "bankroll": record.bankroll,
            "total": record.total,
            "pl_usd": record.pl_usd,
            "pl_pct": record.pl_pct,
            "jobs_solved": record.jobs_solved,
            "primary_provider": record.primary_provider,
            "last_solved_at": record.last_solved_at,
            "next_rebalance_at": record.next_rebalance_at,
            "rebalance_interval_hours": record.rebalance_interval_hours,
            "created_at": record.created_at or now,
            "updated_at": now,
            "environment": self._environment,
        }


class DbJobStore(JobStore):
    """DB write-through audit store."""

    def __init__(
        self,
        database_url: str,
        *,
        environment: str,
        allow_reset: bool = False,
    ) -> None:
        super().__init__()
        self._engine = create_db_engine(database_url)
        self._environment = environment
        self._allow_reset = allow_reset
        metadata.create_all(self._engine)
        self._load()

    @property
    def engine(self) -> Engine:
        return self._engine

    def record(self, agent_id: str, provenance) -> JobRecord:
        job = super().record(agent_id, provenance)
        with self._engine.begin() as conn:
            conn.execute(
                insert(jobs_table),
                {
                    "id": job.id,
                    "agent_id": job.agent_id,
                    "q_hash": job.q_hash,
                    "provider": job.provider,
                    "provider_role": job.provider_role,
                    "solve_time_s": job.solve_time_s,
                    "deadline_s": job.deadline_s,
                    "feasible": job.feasible,
                    "solved_at": job.solved_at,
                    "environment": self._environment,
                },
            )
        return job

    def record_solve_snapshot(
        self,
        *,
        job_id: str,
        agent_id: str,
        sliders: dict[str, Any],
        assets: list[str],
        portfolio: list[dict[str, Any]],
        holdings_units: dict[str, float],
        solver_results: list[dict[str, Any]],
        winner_provider: str,
    ) -> None:
        super().record_solve_snapshot(
            job_id=job_id,
            agent_id=agent_id,
            sliders=sliders,
            assets=assets,
            portfolio=portfolio,
            holdings_units=holdings_units,
            solver_results=solver_results,
            winner_provider=winner_provider,
        )
        with self._engine.begin() as conn:
            conn.execute(
                insert(solve_snapshots_table),
                {
                    "job_id": job_id,
                    "agent_id": agent_id,
                    "sliders": dict(sliders),
                    "assets": list(assets),
                    "portfolio": list(portfolio),
                    "holdings_units": dict(holdings_units),
                    "solver_results": list(solver_results),
                    "winner_provider": winner_provider,
                    "created_at": _now_iso(),
                    "environment": self._environment,
                },
            )

    def reset(self) -> None:
        super().reset()
        if not self._allow_reset:
            return
        with self._engine.begin() as conn:
            for table in (solve_snapshots_table, jobs_table):
                conn.execute(delete(table).where(table.c.environment == self._environment))

    def _load(self) -> None:
        with self._engine.begin() as conn:
            job_rows = conn.execute(
                select(jobs_table).where(jobs_table.c.environment == self._environment)
            ).mappings()
            snapshot_rows = conn.execute(
                select(solve_snapshots_table)
                .where(solve_snapshots_table.c.environment == self._environment)
                .order_by(solve_snapshots_table.c.id)
            ).mappings()
            with self._lock:
                for row in job_rows:
                    job = JobRecord(
                        id=row["id"],
                        agent_id=row["agent_id"],
                        q_hash=row["q_hash"],
                        provider=row["provider"],
                        provider_role=row["provider_role"],
                        solve_time_s=row["solve_time_s"],
                        deadline_s=row["deadline_s"],
                        feasible=row["feasible"],
                        solved_at=row["solved_at"],
                    )
                    self._jobs[job.id] = job
                for row in snapshot_rows:
                    self._solve_snapshots.append(
                        {
                            "job_id": row["job_id"],
                            "agent_id": row["agent_id"],
                            "sliders": dict(row["sliders"]),
                            "assets": list(row["assets"]),
                            "portfolio": list(row["portfolio"]),
                            "holdings_units": dict(row["holdings_units"]),
                            "solver_results": list(row["solver_results"]),
                            "winner_provider": row["winner_provider"],
                            "created_at": row["created_at"],
                        }
                    )


class DbQpuBudgetStore(QpuBudgetStore):
    """SQL-backed QPU budget store, scoped by APP_ENV."""

    def __init__(
        self,
        database_url: str,
        *,
        environment: str,
        allow_reset: bool = False,
    ) -> None:
        super().__init__()
        self._engine = create_db_engine(database_url)
        self._environment = environment
        self._allow_reset = allow_reset
        metadata.create_all(self._engine)

    @property
    def engine(self) -> Engine:
        return self._engine

    def reserve(
        self,
        agent_id: str,
        *,
        source: QpuBudgetSource,
        now: datetime | None = None,
    ) -> QpuBudgetStatus:
        now = _coerce_utc(now)
        with self._lock:
            self._prune(now)
            status = self.status(agent_id, now=now)
            if status.used >= status.limit:
                raise QpuBudgetExceeded(status)
            with self._engine.begin() as conn:
                conn.execute(
                    insert(qpu_budget_events_table),
                    {
                        "agent_id": agent_id,
                        "source": source,
                        "reserved_at": now.isoformat(),
                        "environment": self._environment,
                    },
                )
            return self.status(agent_id, now=now)

    def status(self, agent_id: str, *, now: datetime | None = None) -> QpuBudgetStatus:
        now = _coerce_utc(now)
        with self._lock:
            self._prune(now)
            return _status_from_times(self._event_times(agent_id, now), now=now)

    def reset(self) -> None:
        super().reset()
        if not self._allow_reset:
            return
        with self._engine.begin() as conn:
            conn.execute(
                delete(qpu_budget_events_table).where(
                    qpu_budget_events_table.c.environment == self._environment
                )
            )

    def _event_times(self, agent_id: str, now: datetime) -> list[datetime]:
        cutoff = now - timedelta(seconds=config.QPU_BUDGET_WINDOW_S)
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(qpu_budget_events_table.c.reserved_at)
                .where(qpu_budget_events_table.c.agent_id == agent_id)
                .where(qpu_budget_events_table.c.environment == self._environment)
                .where(qpu_budget_events_table.c.reserved_at > cutoff.isoformat())
            ).scalars()
            return [_parse_iso(row) for row in rows]

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=config.QPU_BUDGET_WINDOW_S)
        with self._engine.begin() as conn:
            conn.execute(
                delete(qpu_budget_events_table)
                .where(qpu_budget_events_table.c.environment == self._environment)
                .where(qpu_budget_events_table.c.reserved_at <= cutoff.isoformat())
            )


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
