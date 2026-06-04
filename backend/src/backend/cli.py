"""Command-line entry point for testing the backend without the HTTP server.

    python -m backend.cli market
    python -m backend.cli optimize --risk 70 --diversification 50
    python -m backend.cli race --diversification 80

Runs against the configured market source (synthetic by default), so you can
inspect what the model derives from the time series (μ, vol, spot), run the full
optimize pipeline, or watch the solver race — all from a terminal.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from . import config
from .api.schemas import AgentConfig, SliderValues
from .financial import basket
from .financial.estimators.covariance import covariance
from .financial.estimators.expected_return import expected_return
from .financial.prices.source import get_source
from .financial.qubo_encoder import encode_qubo
from .financial.slider_map import map_sliders
from .financial.types import MIQPProblem
from .orchestration.job import run_optimization
from .persistence.agents import get_agent_store
from .solvers.feasibility import check_feasibility
from .solvers.providers.gurobi import GurobiProvider
from .solvers.providers.sa import SAProvider
from .solvers.types import SolverFailed


def _sliders(args: argparse.Namespace) -> SliderValues:
    return SliderValues(
        tradingActivity=args.trading_activity,
        riskPreference=args.risk,
        tradeSize=args.trade_size,
        holdingStyle=args.holding_style,
        diversification=args.diversification,
    )


def cmd_market(args: argparse.Namespace) -> None:
    """Dump what the model sees: spot, hourly μ, and hourly vol per asset."""
    source = get_source()
    tickers = list(basket.TICKERS)
    returns = source.hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    mu = expected_return(returns, args.tau)
    vol = np.sqrt(np.diag(covariance(returns)))
    spot = source.spot_prices(tickers)

    print(
        f"source={config.MARKET_DATA_SOURCE}  assets={len(tickers)}  "
        f"Σ-window={config.SIGMA_WINDOW_HOURS}h  μ-window(τ)={args.tau}h"
    )
    print(f"  {'ticker':<8}{'spot':>14}{'μ/hr':>12}{'vol/hr':>12}")
    for i, ticker in enumerate(tickers):
        print(f"  {ticker:<8}{spot[ticker]:>14,.4f}{mu[i]:>12.6f}{vol[i]:>12.6f}")


def cmd_optimize(args: argparse.Namespace) -> None:
    """Create an ephemeral agent, run the full pipeline, print the portfolio."""
    store = get_agent_store()
    agent = store.create(
        AgentConfig(name=args.name, handle=None, sliders=_sliders(args)),
        bankroll=config.BANKROLL_USD,
    )
    params = map_sliders(agent.sliders)
    print(f"agent {agent.id}  bankroll ${agent.bankroll:,.0f}")
    print(
        f"params: γ={params.gamma:.2f}  w_max={params.w_max:.3f}  w_min={params.w_min:.3f}  "
        f"τ={params.tau_hours}h  K={params.K}  λ_t={params.lambda_t}"
    )

    tickers = list(basket.TICKERS)
    outcome = run_optimization(agent.id)
    result = outcome.result
    print(
        f"\nsolved by {result.provider} ({result.provider_type}) in "
        f"{result.solve_time * 1000:.1f} ms · kind={result.kind}"
    )
    print(f"portfolio: {len(result.portfolio)} positions (target K={params.K})")
    print(f"  {'ticker':<8}{'pct':>9}{'usd':>14}")
    for entry in result.portfolio:
        print(f"  {entry.ticker:<8}{entry.pct:>8.2f}%{entry.usd:>14,.2f}")
    print(
        f"  {'total':<8}{sum(e.pct for e in result.portfolio):>8.2f}%"
        f"{sum(e.usd for e in result.portfolio):>14,.2f}"
    )

    # Full solver race — the winner is above; the rest (incl. SA) below. The
    # pipeline already waited for every solver, so this adds no delay.
    print(f"\nsolver race (waited for all, target K={params.K}):")
    for solution in outcome.solver_results:
        feas = check_feasibility(solution.weights, params.K, params.w_max)
        tag = "  ← WINNER" if solution.provider == outcome.winner_provider else ""
        _print_solution(solution.provider, solution.provider_role, solution, feas, tickers, tag)
    winner_sol = next(
        (s for s in outcome.solver_results if s.provider == outcome.winner_provider), None
    )
    classical = [
        s
        for s in outcome.solver_results
        if s.provider != outcome.winner_provider and s.provider_role == "CPU"
    ]
    if winner_sol and classical and winner_sol.solve_time_s > 0:
        slowest = max(classical, key=lambda s: s.solve_time_s)
        print(
            f"\nwinner {result.provider} solved "
            f"~{slowest.solve_time_s / winner_sol.solve_time_s:.0f}× faster than {slowest.provider}"
        )


def _print_solution(provider_name, role, solution, feas, tickers, tag=""):
    nonzero = int((solution.weights > 1e-5).sum())
    print(
        f"  {provider_name:<8}{role:<5}{solution.solve_time_s * 1000:>9.1f} ms  "
        f"feasible={str(feas.feasible):<6}Σw={solution.weights.sum():.3f}  "
        f"nonzero={nonzero}  obj={solution.objective:.5f}{tag}",
        flush=True,
    )
    positions = sorted(
        (
            (tickers[i], float(solution.weights[i]))
            for i in range(len(tickers))
            if solution.weights[i] > 1e-5
        ),
        key=lambda tw: -tw[1],
    )
    alloc = "  ".join(f"{ticker} {weight * 100:.1f}%" for ticker, weight in positions)
    print(f"           {alloc or '(no positions)'}", flush=True)
    if not feas.feasible:
        print(f"           ↳ infeasible: {feas.reason}", flush=True)


def cmd_race(args: argparse.Namespace) -> None:
    """Race the solvers, streaming each result as it finishes (winner shown first)."""
    source = get_source()
    tickers = list(basket.TICKERS)
    params = map_sliders(_sliders(args))
    returns = source.hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    miqp = MIQPProblem(
        mu=expected_return(returns, params.tau_hours),
        Sigma=covariance(returns),
        gamma=params.gamma,
        lambda_t=params.lambda_t,
        w_ref=np.zeros(len(tickers)),
        w_max=params.w_max,
        w_min=params.w_min,
        K=params.K,
        asset_tickers=tickers,
    )
    qubo = encode_qubo(miqp)
    providers = [GurobiProvider(), SAProvider()]
    print(
        f"racing {', '.join(p.name for p in providers)} (target K={miqp.K}) — "
        f"first feasible wins, printed as each finishes\n",
        flush=True,
    )

    winner = None
    results = []
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {}
        for provider in providers:
            if provider.name == "gurobi":
                fut = executor.submit(provider.solve_miqp, miqp, config.SOLVER_DEADLINE_S)
            else:
                fut = executor.submit(provider.solve_qubo, qubo, miqp, config.SOLVER_DEADLINE_S)
            futures[fut] = provider
        # Stream each result the moment it lands; wait for ALL (don't exit on the winner).
        for fut in as_completed(futures):
            provider = futures[fut]
            try:
                solution = fut.result()
            except SolverFailed as exc:
                print(f"  {provider.name:<8}{provider.role:<5} failed: {exc}", flush=True)
                continue
            feas = check_feasibility(solution.weights, miqp.K, miqp.w_max)
            solution.feasible = feas.feasible
            tag = ""
            if feas.feasible and winner is None:
                winner = solution
                tag = "  ← WINNER"
            _print_solution(provider.name, provider.role, solution, feas, tickers, tag)
            results.append(solution)

    if winner is None:
        print("\nno feasible solution from any solver", flush=True)
        return
    classical = [s for s in results if s is not winner and s.provider_role == "CPU"]
    if classical:
        slowest = max(classical, key=lambda s: s.solve_time_s)
        if winner.solve_time_s > 0:
            print(
                f"\nwinner {winner.provider} solved "
                f"~{slowest.solve_time_s / winner.solve_time_s:.0f}× faster than {slowest.provider}",
                flush=True,
            )


def _add_slider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trading-activity", type=int, default=50)
    parser.add_argument("--risk", type=int, default=50, help="risk preference 0–100")
    parser.add_argument("--trade-size", type=int, default=50)
    parser.add_argument("--holding-style", type=int, default=50)
    parser.add_argument("--diversification", type=int, default=50)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="backend.cli", description="QTW backend test CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_market = sub.add_parser("market", help="dump spot, μ and vol per asset")
    p_market.add_argument("--tau", type=int, default=168, help="μ lookback in hours")
    p_market.set_defaults(func=cmd_market)

    p_optimize = sub.add_parser("optimize", help="run the full optimize pipeline")
    p_optimize.add_argument("--name", default="cli")
    _add_slider_args(p_optimize)
    p_optimize.set_defaults(func=cmd_optimize)

    p_race = sub.add_parser("race", help="run one solver race and show all results")
    _add_slider_args(p_race)
    p_race.set_defaults(func=cmd_race)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
