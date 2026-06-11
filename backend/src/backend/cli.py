"""Command-line entry point for testing the backend without the HTTP server.

python -m backend.cli market
python -m backend.cli optimize --risk 70 --assets BTC,ETH,IONQ
python -m backend.cli race --max-position 80
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from . import config
from .api.schemas import AgentConfig, SliderValues
from .financial import basket
from .financial.basket import validate_basket
from .financial.estimators.covariance import covariance
from .financial.estimators.expected_return import expected_return
from .financial.prices.source import get_source
from .financial.qubo_encoder import encode_qubo
from .financial.slider_map import map_sliders
from .financial.types import PortfolioProblem
from .orchestration.job import run_optimization
from .persistence.agents import get_agent_store
from .solvers.feasibility import check_feasibility
from .solvers.router import build_providers
from .solvers.types import SolverFailed


def _sliders(args: argparse.Namespace) -> SliderValues:
    return SliderValues(
        rebalanceFrequency=args.rebalance,
        riskPreference=args.risk,
        maxPositionSize=args.max_position,
    )


def _basket(args: argparse.Namespace) -> list[str]:
    selected = [t.strip().upper() for t in args.assets.split(",")] if args.assets else None
    return validate_basket(selected)


def _build_problem(tickers: list[str], args: argparse.Namespace) -> PortfolioProblem:
    params = map_sliders(_sliders(args), len(tickers))
    returns = get_source().hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    return PortfolioProblem(
        mu=expected_return(returns, config.MU_WINDOW_HOURS),
        Sigma=covariance(returns),
        gamma=params.gamma,
        lambda_t=0.0,  # CLI race is a fresh solve — no holdings to anchor to
        w_ref=np.zeros(len(tickers)),
        w_max=params.w_max,
        w_min=params.w_min,
        asset_tickers=tickers,
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
        ((tickers[i], float(w)) for i, w in enumerate(solution.weights) if w > 1e-5),
        key=lambda tw: -tw[1],
    )
    print(f"           {'  '.join(f'{t} {w * 100:.1f}%' for t, w in positions) or '(none)'}")
    if not feas.feasible:
        print(f"           ↳ infeasible: {feas.reason}")


def cmd_market(args: argparse.Namespace) -> None:
    """Dump what the model sees: spot, hourly μ, and hourly vol per asset."""
    source = get_source()
    tickers = list(basket.TICKERS)
    returns = source.hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    mu = expected_return(returns, config.MU_WINDOW_HOURS)
    vol = np.sqrt(np.diag(covariance(returns)))
    spot = source.spot_prices(tickers)

    print(
        f"source={config.MARKET_DATA_SOURCE}  assets={len(tickers)}  "
        f"Σ-window={config.SIGMA_WINDOW_HOURS}h  μ-window={config.MU_WINDOW_HOURS}h"
    )
    print(f"  {'ticker':<8}{'class':<8}{'spot':>14}{'μ/hr':>12}{'vol/hr':>12}")
    for i, meta in enumerate(basket.BASKET):
        print(
            f"  {meta.ticker:<8}{meta.asset_class:<8}"
            f"{spot[meta.ticker]:>14,.4f}{mu[i]:>12.6f}{vol[i]:>12.6f}"
        )


def cmd_optimize(args: argparse.Namespace) -> None:
    """Create an ephemeral agent, run the full pipeline, print the portfolio."""
    tickers = _basket(args)
    agent = get_agent_store().create(
        AgentConfig(name=args.name, sliders=_sliders(args), assets=tickers),
        bankroll=config.BANKROLL_USD,
    )
    params = map_sliders(agent.sliders, len(tickers))
    print(f"agent {agent.id}  bankroll ${agent.bankroll:,.0f}  basket={len(tickers)} assets")
    print(
        f"params: γ={params.gamma:.2f}  w_max={params.w_max:.3f}  w_min={params.w_min:.3f}  "
        f"rebalance={params.rebalance_hours}h"
    )

    outcome = run_optimization(agent.id)
    result = outcome.result
    print(
        f"\nsolved by {result.provider} ({result.provider_type}) in "
        f"{result.solve_time * 1000:.1f} ms · kind={result.kind}"
    )
    print(f"portfolio: {len(result.portfolio)} positions")
    print(f"  {'ticker':<8}{'pct':>9}{'usd':>14}")
    for entry in result.portfolio:
        print(f"  {entry.ticker:<8}{entry.pct:>8.2f}%{entry.usd:>14,.2f}")
    print(
        f"  {'total':<8}{sum(e.pct for e in result.portfolio):>8.2f}%"
        f"{sum(e.usd for e in result.portfolio):>14,.2f}"
    )

    print("\nsolver race (waited for all):")
    winner_solution = None
    for solution in outcome.solver_results:
        feas = check_feasibility(solution.weights, params.w_max, params.w_min)
        is_winner = solution.provider == outcome.winner_provider
        if is_winner:
            winner_solution = solution
        _print_solution(
            solution.provider,
            solution.provider_role,
            solution,
            feas,
            tickers,
            "  ← WINNER" if is_winner else "",
        )
    _print_speedup(winner_solution, outcome.solver_results, result.provider)


def cmd_race(args: argparse.Namespace) -> None:
    """Race the solvers, streaming each result as it finishes (winner first)."""
    tickers = _basket(args)
    problem = _build_problem(tickers, args)
    qubo = encode_qubo(problem)
    providers = build_providers()
    note = (
        "" if any(p.role == "QPU" for p in providers) else " (set DWAVE_API_TOKEN to add the QPU)"
    )
    print(
        f"racing {', '.join(p.name for p in providers)} over {len(tickers)} assets{note} — "
        f"first feasible wins, printed as each finishes\n",
        flush=True,
    )

    def dispatch(provider):
        if provider.name == "gurobi":
            return provider.solve_qp(problem, config.SOLVER_DEADLINE_S)
        return provider.solve_qubo(qubo, problem, config.SOLVER_DEADLINE_S)

    winner = None
    results = []
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {executor.submit(dispatch, p): p for p in providers}
        for future in as_completed(futures):
            provider = futures[future]
            try:
                solution = future.result()
            except SolverFailed as exc:
                print(f"  {provider.name:<8}{provider.role:<5} failed: {exc}", flush=True)
                continue
            feas = check_feasibility(solution.weights, problem.w_max, problem.w_min)
            solution.feasible = feas.feasible
            tag = ""
            if feas.feasible and winner is None:
                winner = solution
                tag = "  ← WINNER"
            _print_solution(provider.name, provider.role, solution, feas, tickers, tag)
            results.append(solution)

    if winner is None:
        print("\nno feasible solution from any solver")
        return
    _print_speedup(winner, results, winner.provider)


def _print_speedup(winner, results, winner_label) -> None:
    if winner is None or winner.solve_time_s <= 0:
        return
    classical = [s for s in results if s is not winner and s.provider_role == "CPU"]
    if classical:
        slowest = max(classical, key=lambda s: s.solve_time_s)
        print(
            f"\nwinner {winner_label} solved "
            f"~{slowest.solve_time_s / winner.solve_time_s:.0f}× faster than {slowest.provider}"
        )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rebalance", type=int, default=50, help="rebalance frequency 0–100")
    parser.add_argument("--risk", type=int, default=50, help="risk preference 0–100")
    parser.add_argument("--max-position", type=int, default=50, help="max position size 0–100")
    parser.add_argument("--assets", default=None, help="comma-separated basket, e.g. BTC,ETH,IONQ")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="backend.cli", description="QTW backend test CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_market = sub.add_parser("market", help="dump spot, μ and vol per asset")
    p_market.set_defaults(func=cmd_market)

    p_optimize = sub.add_parser("optimize", help="run the full optimize pipeline")
    p_optimize.add_argument("--name", default="cli")
    _add_common_args(p_optimize)
    p_optimize.set_defaults(func=cmd_optimize)

    p_race = sub.add_parser("race", help="run one solver race and show all results")
    _add_common_args(p_race)
    p_race.set_defaults(func=cmd_race)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
