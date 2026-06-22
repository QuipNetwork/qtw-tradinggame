"""HTTP routes — the 4 request/response endpoints mirroring mvp/src/api/mocks.ts.

The WebSocket channel (subscribeAgent) lives in ws.py. The heavy optimize
pipeline runs in a worker thread so the event loop stays responsive; the
resulting events are published on the loop afterwards.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, Query

from .. import config
from ..events.bus import get_bus
from ..financial.basket import validate_basket
from ..financial.prices.assets_api import AssetsApiError
from ..orchestration.job import run_optimization
from ..persistence.agents import get_agent_store
from ..persistence.jobs import get_job_store
from ..persistence.leaderboard import build_leaderboard
from ..persistence.qpu_budget import QpuBudgetExceeded, get_qpu_budget_store
from ..solvers.types import SolverFailed
from .schemas import (
    AgentConfig,
    HealthResponse,
    LeaderboardEntry,
    OptimizeRequest,
    RecentRouting,
    RoutingProviderStat,
    RoutingResult,
    RoutingStats,
    SubmitAgentResponse,
    ValuationHistoryPoint,
)

# How many recent solves to surface for the TV "recent routings" feed.
RECENT_ROUTING_LIMIT = 24

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Cheap container/proxy health check. Does not contact external services."""
    return HealthResponse(
        app_env=config.APP_ENV,
        persistence="sql" if config.DATABASE_URL else "memory",
        market_data_source=config.MARKET_DATA_SOURCE,
        assets_api_base_url=config.ASSETS_API_BASE_URL,
        qpu_configured=bool(os.environ.get("DWAVE_API_TOKEN")),
        gurobi_in_race=config.GUROBI_IN_RACE,
    )


@router.post("/agents", response_model=SubmitAgentResponse)
async def create_agent(config_in: AgentConfig) -> SubmitAgentResponse:
    try:
        validate_basket(config_in.assets)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record = get_agent_store().create(config_in, bankroll=config.BANKROLL_USD)
    return SubmitAgentResponse(
        agent_id=record.id,
        qr_url=f"{config.QR_BASE_URL}/p/{record.id}",
        bankroll=record.bankroll,
    )


@router.get("/agents/{agent_id}", response_model=AgentConfig)
async def get_agent(agent_id: str) -> AgentConfig:
    record = get_agent_store().get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="agent not found")
    config_out = record.to_config()
    config_out.qpu_budget = get_qpu_budget_store().status(agent_id)
    return config_out


@router.post("/agents/{agent_id}/optimize", response_model=RoutingResult)
async def optimize(agent_id: str, body: OptimizeRequest | None = None) -> RoutingResult:
    sliders = body.sliders if body is not None else None
    assets = body.assets if body is not None else None
    try:
        outcome = await asyncio.to_thread(run_optimization, agent_id, sliders, assets)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except QpuBudgetExceeded as exc:
        detail = {
            "message": str(exc),
            "retryAfterSeconds": exc.status.retry_after_seconds,
            "qpuBudget": exc.status.model_dump(by_alias=True),
        }
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(exc.status.retry_after_seconds)},
        ) from exc
    except SolverFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AssetsApiError as exc:
        # Upstream market-data dependency down/bad → 503; generic detail so the internal
        # assets-api URL/path in the exception text isn't leaked to the client.
        raise HTTPException(status_code=503, detail="market data temporarily unavailable") from exc

    bus = get_bus()
    for event in outcome.events:
        bus.publish(event.channel, event.payload)
    return outcome.result


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard() -> list[LeaderboardEntry]:
    return build_leaderboard()


@router.get("/routing-stats", response_model=RoutingStats)
async def routing_stats() -> RoutingStats:
    store = get_job_store()
    jobs = store.all()
    total = len(jobs)
    qpu_wins = sum(1 for job in jobs if job.provider_role == "QPU")
    cpu_wins = sum(1 for job in jobs if job.provider_role == "CPU")
    provider_counts: dict[tuple[str, str], int] = {}
    for job in jobs:
        key = (job.provider, job.provider_role)
        provider_counts[key] = provider_counts.get(key, 0) + 1

    providers = [
        RoutingProviderStat(
            provider=provider,
            provider_type=provider_type,
            count=count,
            pct=_pct(count, total),
        )
        for (provider, provider_type), count in sorted(
            provider_counts.items(), key=lambda item: (-item[1], item[0][0])
        )
    ]
    # Recent routings feed (newest first) for the TV roulette strip. Winner +
    # timestamp come from the job log; the runner-up time (for the head-to-head
    # comparison) comes from the matching solve snapshot when one is available.
    snapshots_by_job = {snap["job_id"]: snap for snap in store.solve_snapshots()}
    recent: list[RecentRouting] = []
    for job in reversed(jobs[-RECENT_ROUTING_LIMIT:]):
        vs_time: float | None = None
        snap = snapshots_by_job.get(job.id)
        if snap:
            others = [
                run["solveTime"]
                for run in snap.get("solver_results", [])
                if run.get("provider") != snap.get("winner_provider")
                and run.get("solveTime") is not None
            ]
            if others:
                vs_time = min(others)
        recent.append(
            RecentRouting(
                provider=job.provider,
                provider_type=job.provider_role,
                solve_time=job.solve_time_s,
                vs_time=vs_time,
                solved_at=job.solved_at,
            )
        )

    return RoutingStats(
        total=total,
        qpu_wins=qpu_wins,
        cpu_wins=cpu_wins,
        qpu_pct=_pct(qpu_wins, total),
        cpu_pct=_pct(cpu_wins, total),
        providers=providers,
        recent=recent,
    )


@router.get("/agents/{agent_id}/valuation-history", response_model=list[ValuationHistoryPoint])
async def valuation_history(
    agent_id: str,
    limit: int = Query(default=60, ge=1, le=240),
) -> list[ValuationHistoryPoint]:
    store = get_agent_store()
    if store.get(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return store.valuation_history(agent_id, limit=limit)


def _pct(count: int, total: int) -> float:
    return round((count / total) * 100.0, 1) if total else 0.0
