"""End-to-end optimization job — the build-and-solve pipeline for one request.

slider_map → estimates(μ, Σ) → MIQPProblem → solver race → retune → persist.
First-solve vs retune is decided here from whether the agent already holds
positions; the solvers never see the difference.

This function is synchronous and pure w.r.t. I/O side effects beyond the stores
it is handed — it returns the RoutingResult plus the events to publish, rather
than touching the event bus itself, so the API layer can run it in a worker
thread and publish on the event loop. See BACKEND_DAG.md §"Solver race".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config
from ..api.schemas import RoutingResult, SliderValues
from ..financial import basket
from ..financial.estimators.covariance import covariance
from ..financial.estimators.expected_return import expected_return
from ..financial.pnl import mark_to_market
from ..financial.prices.base import MarketDataSource
from ..financial.prices.source import get_source
from ..financial.qubo_decoder import weights_to_portfolio
from ..financial.retune import compute_retune
from ..financial.slider_map import map_sliders
from ..financial.types import MIQPProblem
from ..persistence.agents import AgentStore, get_agent_store
from ..persistence.jobs import JobStore, get_job_store
from ..solvers.router import race
from ..solvers.types import ProviderProvenance, Solution

# Friendly provider names for the "solved by" badge.
_PROVIDER_LABELS = {
    "gurobi": "Gurobi",
    "sa": "Simulated Annealing",
    "dwave": "D-Wave Advantage",
}


@dataclass(frozen=True)
class Event:
    channel: str
    payload: dict


@dataclass(frozen=True)
class OptimizeOutcome:
    result: RoutingResult
    events: list[Event]
    solver_results: list[Solution]  # every solver's result (for inspection/CLI)
    winner_provider: str  # raw provider name of the winner (e.g. "gurobi")


def run_optimization(
    agent_id: str,
    sliders: SliderValues | None = None,
    *,
    agents: AgentStore | None = None,
    jobs: JobStore | None = None,
    market: MarketDataSource | None = None,
    deadline_s: float | None = None,
) -> OptimizeOutcome:
    """Run one optimization job for an agent and return its outcome.

    Raises KeyError if the agent is unknown, or SolverFailed if no solver
    returns a feasible solution before the deadline.
    """
    agents = agents if agents is not None else get_agent_store()
    jobs = jobs if jobs is not None else get_job_store()
    market = market if market is not None else get_source()

    agent = agents.get(agent_id)
    if agent is None:
        raise KeyError(f"unknown agent {agent_id!r}")

    if sliders is not None:
        agents.update_sliders(agent_id, sliders)
        agent = agents.get(agent_id)

    params = map_sliders(agent.sliders)
    tickers = list(basket.TICKERS)

    # Estimates: Σ over the fixed 720h window, μ over the τ sub-window of it.
    returns = market.hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    Sigma = covariance(returns)
    mu = expected_return(returns, params.tau_hours)

    # Current state → first solve (no holdings) vs retune (drifted holdings).
    spot = market.spot_prices(tickers)
    is_first = not agent.holdings_units
    if is_first:
        portfolio_value = agent.bankroll
        w_old = np.zeros(len(tickers))
    else:
        portfolio_value = sum(units * spot[t] for t, units in agent.holdings_units.items())
        w_old = np.array(
            [
                (agent.holdings_units.get(t, 0.0) * spot[t] / portfolio_value)
                if portfolio_value > 0
                else 0.0
                for t in tickers
            ]
        )

    w_ref = np.zeros(len(tickers)) if is_first else w_old.copy()
    miqp = MIQPProblem(
        mu=mu,
        Sigma=Sigma,
        gamma=params.gamma,
        lambda_t=params.lambda_t,
        w_ref=w_ref,
        w_max=params.w_max,
        w_min=params.w_min,
        K=params.K,
        asset_tickers=tickers,
    )

    race_result = race(miqp, deadline_s=deadline_s)
    winner = race_result.winner
    w_new = winner.weights

    # Diff into trades + (V0-zero) fee, then convert target USD → token units.
    retune = compute_retune(w_old, w_new, tickers, portfolio_value)
    investable = portfolio_value - retune.fee_usd
    holdings_units = {t: usd / spot[t] for t, usd in retune.new_holdings_usd.items()}

    # Persist holdings + valuation + audit record.
    agents.apply_solve(
        agent_id,
        holdings_units=holdings_units,
        total=investable,
        provider_type=winner.provider_role,
    )
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
        provider=_PROVIDER_LABELS.get(winner.provider, winner.provider),
        provider_type=winner.provider_role,
        solve_time=winner.solve_time_s,
        vs_classical=race_result.vs_classical,
        portfolio=weights_to_portfolio(w_new, tickers, investable),
        kind="first" if is_first else "retune",
        job_id=job.id,
        solved_at=job.solved_at,
        fee_usd=retune.fee_usd,
    )

    # Events: an immediate valuation for the phone, plus a new-agent TV splash.
    update = mark_to_market(holdings_units, spot, agent.bankroll)
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
