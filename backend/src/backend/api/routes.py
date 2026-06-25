"""HTTP routes mirroring the MVP API contract in mvp/src/api.

The WebSocket channel (subscribeAgent) lives in ws.py. The heavy optimize
pipeline runs in a worker thread so the event loop stays responsive; the
resulting events are published on the loop afterwards.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from .. import config
from ..events.bus import get_bus
from ..financial.basket import validate_basket
from ..financial.prices.assets_api import AssetsApiError
from ..notifications.dispatch import maybe_send_update_email
from ..notifications.email import send_signup_confirmation
from ..orchestration.job import run_optimization
from ..persistence.agents import AgentRecord, EmailAlreadyRegistered, get_agent_store
from ..persistence.jobs import get_job_store
from ..persistence.leaderboard import build_leaderboard
from ..persistence.qpu_budget import QpuBudgetExceeded, get_qpu_budget_store
from ..solvers.router import classify_outcome
from ..solvers.types import SolverFailed
from .auth import new_agent_token, require_agent_token
from .schemas import (
    AgentConfig,
    AgentPatch,
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
log = logging.getLogger(__name__)


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


def _require_kiosk(request: Request) -> bool:
    """Enforce the booth-kiosk gate. Returns True when the request carries a valid
    X-Kiosk-Key (a trusted kiosk → the per-IP signup limit is skipped). When
    KIOSK_SIGNUP_KEY is unset the gate is off and signups are untrusted (normal
    per-IP limiting). A configured key with a missing/wrong header is rejected 403."""
    if not config.KIOSK_SIGNUP_KEY:
        return False
    provided = request.headers.get("x-kiosk-key", "")
    if not secrets.compare_digest(provided, config.KIOSK_SIGNUP_KEY):
        raise HTTPException(status_code=403, detail="sign-ups are limited to the booth kiosk")
    return True


@router.post("/agents", response_model=SubmitAgentResponse)
async def create_agent(
    config_in: AgentConfig, request: Request, background_tasks: BackgroundTasks
) -> SubmitAgentResponse:
    trusted = _require_kiosk(request)
    retry_after = request.app.state.signup_limiter.check(_client_ip(request), trusted=trusted)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="too many sign-ups from this device; try again shortly",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        validate_basket(config_in.assets)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    token, token_hash = new_agent_token()
    try:
        record = get_agent_store().create(
            config_in, bankroll=config.BANKROLL_USD, token_hash=token_hash
        )
    except EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=409, detail="an agent already exists for this email"
        ) from exc
    background_tasks.add_task(_send_signup_confirmation_email, record, token)
    return SubmitAgentResponse(
        agent_id=record.id,
        # Token in the URL fragment — never sent to the server, so it stays out of logs.
        qr_url=f"{config.QR_BASE_URL}/p/{record.id}#t={token}",
        bankroll=record.bankroll,
        token=token,
    )


def _send_signup_confirmation_email(record: AgentRecord, token: str) -> None:
    """Send the signup email with the secure agent link to anyone who gave an email.

    Transactional (the link is their way back to the agent), so it is not gated on
    the result-email opt-in. Email send failures are logged and never break signup.
    """
    if not record.email:
        return
    link = f"{config.QR_BASE_URL}/p/{record.id}#t={token}"
    try:
        send_signup_confirmation(
            to=record.email,
            name=record.name,
            link=link,
            updates_opt_in=record.updates_opt_in is True,
        )
    except Exception:
        log.warning("signup confirmation email failed agent_id=%s", record.id, exc_info=True)


@router.get(
    "/agents/{agent_id}", response_model=AgentConfig, dependencies=[Depends(require_agent_token)]
)
async def get_agent(agent_id: str) -> AgentConfig:
    record = get_agent_store().get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="agent not found")
    config_out = record.to_config()
    config_out.qpu_budget = get_qpu_budget_store().status(agent_id)
    return config_out


@router.patch(
    "/agents/{agent_id}", response_model=AgentConfig, dependencies=[Depends(require_agent_token)]
)
async def update_agent(agent_id: str, body: AgentPatch) -> AgentConfig:
    store = get_agent_store()
    if store.get(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        assets = validate_basket(body.assets) if body.assets is not None else None
        if body.sliders is not None:
            store.update_sliders(agent_id, body.sliders)
        if assets is not None:
            store.update_assets(agent_id, assets)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = store.get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="agent not found")
    config_out = record.to_config()
    config_out.qpu_budget = get_qpu_budget_store().status(agent_id)
    return config_out


# Process-wide cap on concurrent solves so a burst of retunes can't exhaust the
# worker-thread pool or hammer assets-api / the QPU. Single-worker deploy → one gate.
_solve_semaphore = asyncio.Semaphore(config.SOLVE_CONCURRENCY)


@router.post(
    "/agents/{agent_id}/optimize",
    response_model=RoutingResult,
    dependencies=[Depends(require_agent_token)],
)
async def optimize(
    agent_id: str, background_tasks: BackgroundTasks, body: OptimizeRequest | None = None
) -> RoutingResult:
    # Admin-disabled agents are cut off from solving — reject before the QPU race.
    record = get_agent_store().get(agent_id)
    if record is not None and record.disabled:
        raise HTTPException(status_code=403, detail="agent is disabled")
    sliders = body.sliders if body is not None else None
    assets = body.assets if body is not None else None
    try:
        async with _solve_semaphore:
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
    refreshed = get_agent_store().get(agent_id)
    if refreshed is not None:
        background_tasks.add_task(
            maybe_send_update_email, refreshed, now=datetime.now(UTC), store=get_agent_store()
        )
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
        outcome = "quality"
        snap = snapshots_by_job.get(job.id)
        if snap:
            runs = snap.get("solver_results", [])
            winner_provider = snap.get("winner_provider")
            timed = [
                run["solveTime"]
                for run in runs
                if run.get("provider") != winner_provider and run.get("solveTime") is not None
            ]
            if timed:
                vs_time = min(timed)
            # Classify HOW the winner won — same logic as the live race — so the TV reports a genuine
            # tie instead of a misleading "X% faster" on a quality+speed tie.
            win = next((run for run in runs if run.get("provider") == winner_provider), None)
            scored = [
                run
                for run in runs
                if run.get("provider") != winner_provider
                and run.get("objective") is not None
                and run.get("feasible", True)  # only a FEASIBLE runner-up is a real head-to-head
            ]
            runner = min(scored, key=lambda run: run["objective"]) if scored else None
            if win is not None:
                outcome = classify_outcome(
                    win.get("objective"),
                    win.get("solveTime"),
                    runner.get("objective") if runner else None,
                    runner.get("solveTime") if runner else None,
                )
        recent.append(
            RecentRouting(
                provider=job.provider,
                provider_type=job.provider_role,
                solve_time=job.solve_time_s,
                vs_time=vs_time,
                solved_at=job.solved_at,
                outcome=outcome,
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


@router.get(
    "/agents/{agent_id}/valuation-history",
    response_model=list[ValuationHistoryPoint],
    dependencies=[Depends(require_agent_token)],
)
async def valuation_history(
    agent_id: str,
    limit: int = Query(default=60, ge=1, le=240),
) -> list[ValuationHistoryPoint]:
    store = get_agent_store()
    if store.get(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return store.valuation_history(agent_id, limit=limit)


def _client_ip(request: Request) -> str:
    """Trusted client IP for rate-limit keying.

    The app is reachable only via Caddy (binds 127.0.0.1), which OVERWRITES
    X-Real-IP with the real peer — prefer that. Fall back to the LAST (Caddy-
    appended, non-spoofable) X-Forwarded-For hop. The leftmost XFF entries are
    client-supplied and must never be trusted (they'd let a client mint a fresh
    rate-limit bucket per request). Validate the result parses as an IP before
    using it as a bucket key.
    """
    candidate = request.headers.get("x-real-ip")
    if not candidate:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.rsplit(",", 1)[-1].strip()
    if candidate:
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def _pct(count: int, total: int) -> float:
    return round((count / total) * 100.0, 1) if total else 0.0
