"""SQL-backed persistence stores.

`DATABASE_URL` enables these stores for Supabase/Postgres deployment. Tests can
instantiate them against SQLite, while the default app path stays in-memory when
the env var is unset.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

from ..api.schemas import AgentConfig, AgentUpdate, SliderValues
from .agents import AgentRecord, AgentStore
from .jobs import JobRecord, JobStore

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
    Column("rebalance_interval_hours", Integer, nullable=True),
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


def create_db_engine(database_url: str) -> Engine:
    return create_engine(_normalize_database_url(database_url), future=True)


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
                "rebalance_interval_hours": "INTEGER",
            },
        )
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
                    self._agents.pop(record.id, None)
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

    def record_valuation_snapshot(self, agent_id: str, update_: AgentUpdate) -> None:
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
            rows = conn.execute(
                select(jobs_table).where(jobs_table.c.environment == self._environment)
            ).mappings()
            with self._lock:
                for row in rows:
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
