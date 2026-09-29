"""Job audit log — one record per solved Q hash.

The base store is process-local for tests/offline runs. `DATABASE_URL` swaps the
singleton to `DbJobStore`, which writes job records and solve snapshots to SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from ..solvers.types import ProviderProvenance


@dataclass(frozen=True)
class JobRecord:
    id: str
    agent_id: str
    q_hash: str
    provider: str
    provider_role: str
    solve_time_s: float
    deadline_s: float
    feasible: bool
    solved_at: str


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._solve_snapshots: list[dict[str, Any]] = []
        self._lock = RLock()

    def record(self, agent_id: str, provenance: ProviderProvenance) -> JobRecord:
        with self._lock:
            job = JobRecord(
                id=uuid4().hex[:12],
                agent_id=agent_id,
                q_hash=provenance.q_hash,
                provider=provenance.provider,
                provider_role=provenance.provider_role,
                solve_time_s=provenance.solve_time_s,
                deadline_s=provenance.deadline_s,
                feasible=provenance.feasible,
                solved_at=datetime.now(UTC).isoformat(),
            )
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[JobRecord]:
        with self._lock:
            return list(self._jobs.values())

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
        with self._lock:
            self._solve_snapshots.append(
                {
                    "job_id": job_id,
                    "agent_id": agent_id,
                    "sliders": dict(sliders),
                    "assets": list(assets),
                    "portfolio": list(portfolio),
                    "holdings_units": dict(holdings_units),
                    "solver_results": list(solver_results),
                    "winner_provider": winner_provider,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )

    def update_solver_result(self, job_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        """Replace the job snapshot's entry for `result["provider"]` (a solver that finishes
        after the race, e.g. a Quip order); return the snapshot's updated solver results.

        Raises KeyError if the job has no snapshot or the snapshot has no such provider.
        """
        with self._lock:
            snapshot = next((s for s in self._solve_snapshots if s["job_id"] == job_id), None)
            if snapshot is None:
                raise KeyError(f"no solve snapshot for job {job_id!r}")
            results = snapshot["solver_results"]
            index = next(
                (i for i, r in enumerate(results) if r["provider"] == result["provider"]), None
            )
            if index is None:
                raise KeyError(f"job {job_id!r} has no {result['provider']!r} result")
            results[index] = dict(result)
            return list(results)

    def fail_pending_results(self, error: str) -> dict[str, list[dict[str, Any]]]:
        """Mark every `pending` solver result as `failed` with `error`; return the changed
        snapshots' solver results by job id. Run at startup: a pending result belongs to an
        order the previous process never finished recording."""
        changed: dict[str, list[dict[str, Any]]] = {}
        with self._lock:
            for snapshot in self._solve_snapshots:
                results = snapshot["solver_results"]
                for index, result in enumerate(results):
                    if result.get("status") == "pending":
                        results[index] = {**result, "status": "failed", "error": error}
                        changed[snapshot["job_id"]] = list(results)
        return changed

    def solve_snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._solve_snapshots)

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._solve_snapshots.clear()


_store: JobStore | None = None


def get_job_store() -> JobStore:
    """Return the process-wide job store singleton."""
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def set_job_store(store: JobStore | None) -> None:
    """Override the process-wide store for tests; None rebuilds from config."""
    global _store
    _store = store


def _build_store() -> JobStore:
    from .. import config

    if config.DATABASE_URL:
        from .db import DbJobStore

        return DbJobStore(config.DATABASE_URL, environment=config.APP_ENV)
    return JobStore()
