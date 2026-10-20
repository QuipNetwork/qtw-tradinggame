"""End-to-end optimization job for one request.

basket → slider_map → estimates(μ, Σ) → solver race → allocate → persist.
Every solve is a fresh allocation: a retune liquidates all holdings at spot
and reallocates the full value over the (possibly re-selected) basket. Returns
the result plus the events to publish so the API layer can run this in a
worker thread and publish on the event loop. A Quip order finishes later on its
own worker thread, which records the result and publishes it through
`EventBus.publish_threadsafe`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import config
from ..api.schemas import (
    AgentUpdate,
    PortfolioEntry,
    RoutingResult,
    SliderValues,
    SolverResult,
)
from ..events.bus import get_bus
from ..events.feeds import agent_channel
from ..financial.basket import get_asset, validate_basket
from ..financial.estimators.covariance import covariance
from ..financial.estimators.expected_return import expected_return
from ..financial.pnl import mark_to_market
from ..financial.prices.base import MarketDataSource
from ..financial.prices.source import get_source
from ..financial.qubo_decoder import weights_to_portfolio
from ..financial.qubo_encoder import resolve_frustration_beta
from ..financial.slider_map import map_sliders
from ..financial.types import PortfolioProblem
from ..persistence.agents import AgentRecord, AgentStore, get_agent_store
from ..persistence.jobs import JobRecord, JobStore, get_job_store
from ..persistence.qpu_budget import (
    QpuBudgetExceeded,
    QpuBudgetSource,
    QpuBudgetStore,
    get_qpu_budget_store,
)
from ..solvers import quip_orders
from ..solvers.providers import dwave
from ..solvers.providers.xquad import selected_backend
from ..solvers.router import SolverRun, classify_outcome, race
from ..solvers.types import ProviderProvenance, Solution

_PROVIDER_LABELS = {
    "gurobi": "Gurobi",
    "sa": "Simulated Annealing",
    "dwave": "D-Wave Advantage",
    "xquad-quip": "Quip testnet (xquad)",
    "xquad-dwave-qpu": "D-Wave via xquad",
    "xquad-dwave-cpu": "Local CPU via xquad",
}


@dataclass(frozen=True)
class Event:
    channel: str
    payload: dict


@dataclass(frozen=True)
class OptimizeOutcome:
    result: RoutingResult
    events: list[Event]
    solver_results: list[Solution]
    winner_provider: str


def run_optimization(
    agent_id: str,
    sliders: SliderValues | None = None,
    assets: list[str] | None = None,
    *,
    agents: AgentStore | None = None,
    jobs: JobStore | None = None,
    market: MarketDataSource | None = None,
    qpu_budget: QpuBudgetStore | None = None,
    source: QpuBudgetSource = "manual",
    deadline_s: float | None = None,
) -> OptimizeOutcome:
    """Run one job. Raises KeyError for unknown agents, ValueError for a bad
    basket, SolverFailed when the race produces nothing feasible."""
    agents = agents if agents is not None else get_agent_store()
    jobs = jobs if jobs is not None else get_job_store()
    market = market if market is not None else get_source()
    qpu_budget = qpu_budget if qpu_budget is not None else get_qpu_budget_store()

    agent = agents.get(agent_id)
    if agent is None:
        raise KeyError(f"unknown agent {agent_id!r}")

    candidate_sliders = sliders if sliders is not None else agent.sliders
    tickers = validate_basket(assets if assets is not None else agent.assets)
    params = map_sliders(candidate_sliders, len(tickers))
    backend = selected_backend()
    # A Quip order is paid and slow, so only a manual solve proposes one; it runs outside the
    # race (solvers/quip_orders.py). Scheduled rebalances race the local solvers only.
    quip_order = backend == "quip" and source == "manual"
    include_qpu = (
        quip_order or backend == "dwave-qpu" or (backend is None and dwave.is_configured())
    )
    if include_qpu:
        status = qpu_budget.status(agent_id)
        if status.used >= status.limit:
            raise QpuBudgetExceeded(status)

    # Σ over the fixed 720h window, μ over the fixed lookback within it.
    returns = market.hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    classes = [get_asset(t).asset_class for t in tickers]
    problem = PortfolioProblem(
        mu=expected_return(returns, config.MU_WINDOW_HOURS),
        Sigma=covariance(returns, classes),
        gamma=params.gamma,
        w_max=params.w_max,
        w_min=params.w_min,
        asset_tickers=tickers,
        cardinality_k=params.cardinality_k,  # None in convex mode
        n_units_M=params.n_units_M,
        u_min_units=params.u_min_units,
    )
    # β is config'd as a fraction of the objective scale (select encoding) → effective absolute β.
    problem.frustration_beta = resolve_frustration_beta(problem)

    qpu_budget_status = (
        qpu_budget.reserve(agent_id, source=source) if include_qpu else qpu_budget.status(agent_id)
    )
    race_result = race(problem, deadline_s=deadline_s, include_qpu=include_qpu)
    winner = race_result.winner
    # The response reports the Quip order pending; its result replaces that entry in the
    # job's solve snapshot once the order finalizes.
    late_results = [quip_orders.pending_result()] if quip_order else []

    # Liquidate everything at spot, reallocate the full value by the winner's
    # weights. The spot snapshot covers old and new holdings alike.
    spot = market.spot_prices(list({*tickers, *agent.holdings_units}))
    is_first = not agent.holdings_units
    portfolio_value = (
        agent.bankroll
        if is_first
        else sum(units * spot[t] for t, units in agent.holdings_units.items())
    )
    holdings_units = {
        t: w * portfolio_value / spot[t]
        for t, w in zip(tickers, winner.weights, strict=True)
        if w > 0.0
    }

    if sliders is not None:
        agents.update_sliders(agent_id, sliders)
    if assets is not None:
        agents.update_assets(agent_id, tickers)

    agents.apply_solve(
        agent_id,
        holdings_units=holdings_units,
        total=portfolio_value,
        provider_type=winner.provider_role,
    )
    scheduled_agent = agents.get(agent_id)
    provenance = ProviderProvenance(
        provider=winner.provider,
        provider_role=winner.provider_role,
        q_hash=race_result.q_hash,
        deadline_s=deadline_s if deadline_s is not None else config.RACE_OVERALL_DEADLINE_S,
        solve_time_s=winner.solve_time_s,
        feasible=winner.feasible,
    )
    job = jobs.record(agent_id, provenance)

    result = RoutingResult(
        provider=provider_label(winner.provider),
        provider_type=winner.provider_role,
        solve_time=winner.solve_time_s,
        vs_classical=race_result.vs_classical,
        portfolio=weights_to_portfolio(winner.weights, tickers, portfolio_value),
        solver_results=[
            _solver_run_result(run, winner_provider=winner.provider)
            for run in race_result.solver_runs
        ]
        + [_snapshot_solver_result(summary) for summary in late_results],
        outcome=race_result.outcome,
        kind="first" if is_first else "retune",
        job_id=job.id,
        solved_at=job.solved_at,
        next_rebalance_at=scheduled_agent.next_rebalance_at if scheduled_agent else None,
        rebalance_interval_hours=(
            scheduled_agent.rebalance_interval_hours if scheduled_agent else None
        ),
        qpu_budget=qpu_budget_status,
    )
    jobs.record_solve_snapshot(
        job_id=job.id,
        agent_id=agent_id,
        sliders=(scheduled_agent.sliders if scheduled_agent else candidate_sliders).model_dump(
            by_alias=True
        ),
        assets=tickers,
        portfolio=[entry.model_dump() for entry in result.portfolio],
        holdings_units=holdings_units,
        solver_results=[_solver_run_summary(run) for run in race_result.solver_runs] + late_results,
        winner_provider=winner.provider,
    )
    if quip_order:
        submitted = quip_orders.submit(
            problem,
            lambda quip_result: _record_late_result(agents, jobs, agent_id, job.id, quip_result),
        )
        if submitted is None:  # too many orders pending: this solve proposes none
            skipped = quip_orders.skipped_result()
            jobs.update_solver_result(job.id, skipped)
            result.solver_results[-1] = _snapshot_solver_result(skipped)

    update = mark_to_market(holdings_units, spot, agent.bankroll)
    update.next_rebalance_at = scheduled_agent.next_rebalance_at if scheduled_agent else None
    update.rebalance_interval_hours = (
        scheduled_agent.rebalance_interval_hours if scheduled_agent else None
    )
    update.qpu_budget = qpu_budget_status
    events = [Event(channel=f"agent:{agent_id}", payload=update.model_dump(by_alias=True))]
    if is_first:
        events.append(
            Event(
                channel="tv",
                payload={
                    "type": "new-agent",
                    "agentId": agent_id,
                    "name": agent.name,
                    "handle": agent.handle,
                },
            )
        )
    return OptimizeOutcome(
        result=result,
        events=events,
        solver_results=race_result.all_results,
        winner_provider=winner.provider,
    )


def _solver_run_result(run: SolverRun, *, winner_provider: str) -> SolverResult:
    return SolverResult(
        provider=provider_label(run.provider),
        providerType=run.provider_role,
        status="winner" if run.provider == winner_provider else run.status,
        feasible=run.feasible,
        solveTime=run.solve_time_s,
        raceTime=run.race_time_s,
        objective=run.objective,
        bestObjective=run.best_objective,
        error=run.error,
        orderId=run.order_id,
    )


def provider_label(provider: str) -> str:
    """The display name of a provider key, e.g. "sa" → "Simulated Annealing"."""
    return _PROVIDER_LABELS.get(provider, provider)


def _snapshot_solver_result(summary: dict) -> SolverResult:
    """A snapshot summary row as a response row. Rows written before late results existed
    lack bestObjective and orderId, so the optional fields default."""
    return SolverResult(
        provider=provider_label(summary["provider"]),
        providerType=summary["providerRole"],
        status=summary["status"],
        feasible=summary["feasible"],
        solveTime=summary.get("solveTime"),
        raceTime=summary.get("raceTime"),
        objective=summary.get("objective"),
        bestObjective=summary.get("bestObjective", False),
        error=summary.get("error"),
        orderId=summary.get("orderId"),
    )


def race_comparison(runs: list[dict], winner_provider: str | None) -> tuple[str, dict | None]:
    """How the winner won against its best feasible race runner-up, from snapshot rows.

    A Quip order runs outside the race, so its row is never the runner-up. Equal objectives
    go to the faster solver, as on the phone and kiosk. Returns the outcome (see
    classify_outcome) and the runner-up row, or None when there is none.
    """
    win = next((run for run in runs if run.get("provider") == winner_provider), None)
    scored = [
        run
        for run in runs
        if run.get("provider") != winner_provider
        and run.get("providerRole") != quip_orders.ROLE
        and run.get("objective") is not None
        and run.get("feasible", True)
    ]
    runner = (
        min(scored, key=lambda run: (run["objective"], run.get("solveTime") or math.inf))
        if scored
        else None
    )
    if win is None:
        return "quality", runner
    outcome = classify_outcome(
        win.get("objective"),
        win.get("solveTime"),
        runner.get("objective") if runner else None,
        runner.get("solveTime") if runner else None,
    )
    return outcome, runner


def routing_result_from_snapshot(job: JobRecord, snapshot: dict) -> RoutingResult:
    """Rebuild a stored solve as the optimize response, minus the fields that describe the
    agent now rather than the solve (rebalance schedule, QPU budget)."""
    rows = snapshot["solver_results"]
    outcome, _runner = race_comparison(rows, snapshot["winner_provider"])
    return RoutingResult(
        provider=provider_label(job.provider),
        provider_type=job.provider_role,
        solve_time=job.solve_time_s,
        vs_classical=1.0,  # legacy field; not recorded with the snapshot
        portfolio=[PortfolioEntry(**entry) for entry in snapshot["portfolio"]],
        solver_results=[_snapshot_solver_result(row) for row in rows],
        outcome=outcome,
        job_id=job.id,
        solved_at=job.solved_at,
    )


def _record_late_result(
    agents: AgentStore, jobs: JobStore, agent_id: str, job_id: str, late_result: dict
) -> None:
    """Store a solver result that finished after the race, then push the job's rows to the
    agent's open pages. Runs on the Quip order worker thread."""
    rows = jobs.update_solver_result(job_id, late_result)
    record = agents.get(agent_id)
    if record is None:
        return
    get_bus().publish_threadsafe(
        agent_channel(agent_id), _solver_results_frame(record, job_id, rows)
    )


def _solver_results_frame(record: AgentRecord, job_id: str, rows: list[dict]) -> dict:
    """A "solver-results" frame for the agent channel.

    Frontends from before this frame pass every agent frame to their live-valuation state,
    so it carries a full valuation update from the agent record too. Drop that part once
    those tabs are gone.
    """
    valuation = AgentUpdate(
        plUSD=record.pl_usd,
        plPct=record.pl_pct,
        total=record.total,
        asOf=record.valuation_as_of,
        stale=record.valuation_stale,
        nextRebalanceAt=record.next_rebalance_at,
        rebalanceIntervalHours=record.rebalance_interval_hours,
    )
    return {
        **valuation.model_dump(by_alias=True),
        "type": "solver-results",
        "jobId": job_id,
        "solverResults": [_snapshot_solver_result(row).model_dump(by_alias=True) for row in rows],
    }


def _solver_run_summary(run: SolverRun) -> dict:
    return {
        "provider": run.provider,
        "providerRole": run.provider_role,
        "status": run.status,
        "feasible": run.feasible,
        "solveTime": run.solve_time_s,
        "raceTime": run.race_time_s,
        "objective": run.objective,
        "bestObjective": run.best_objective,
        "error": run.error,
        "orderId": run.order_id,
    }
