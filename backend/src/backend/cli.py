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
from .financial.prices.assets_api import AssetsApiError
from .financial.prices.source import get_source
from .financial.qubo_encoder import encode_qubo, resolve_frustration_beta
from .financial.slider_map import map_sliders
from .financial.types import PortfolioProblem, correlation_matrix
from .orchestration.job import run_optimization
from .persistence.agents import get_agent_store
from .solvers.feasibility import check_feasibility
from .solvers.router import build_providers, pick_winner
from .solvers.types import SolverFailed


def _sliders(args: argparse.Namespace) -> SliderValues:
    return SliderValues(
        rebalanceFrequency=args.rebalance,
        riskPreference=args.risk,
        maxPositionSize=args.max_position,
        holdCount=getattr(args, "hold_count", None),
    )


def _basket(args: argparse.Namespace) -> list[str]:
    selected = [t.strip().upper() for t in args.assets.split(",")] if args.assets else None
    return validate_basket(selected)


def _build_problem(tickers: list[str], args: argparse.Namespace) -> PortfolioProblem:
    params = map_sliders(_sliders(args), len(tickers))
    returns = get_source().hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    classes = [basket.get_asset(t).asset_class for t in tickers]
    problem = PortfolioProblem(
        mu=expected_return(returns, config.MU_WINDOW_HOURS),
        Sigma=covariance(returns, classes),
        gamma=params.gamma,
        w_max=params.w_max,
        w_min=params.w_min,
        asset_tickers=tickers,
        cardinality_k=params.cardinality_k,
        n_units_M=params.n_units_M,
        u_min_units=params.u_min_units,
    )
    problem.frustration_beta = resolve_frustration_beta(problem)
    return problem


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
    classes = [basket.get_asset(t).asset_class for t in tickers]
    mu = expected_return(returns, config.MU_WINDOW_HOURS)
    vol = np.sqrt(np.diag(covariance(returns, classes)))
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
        feas = check_feasibility(
            solution.weights, params.w_max, params.w_min, cardinality_k=params.cardinality_k
        )
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
    """Race the solvers, then pick the winner per RACE_WINNER_BY (best portfolio by default)."""
    tickers = _basket(args)
    problem = _build_problem(tickers, args)
    qubo = encode_qubo(problem)
    providers = build_providers()
    note = (
        "" if any(p.role == "QPU" for p in providers) else " (set DWAVE_API_TOKEN to add the QPU)"
    )
    by_quality = config.RACE_WINNER_BY == "objective"
    print(
        f"racing {', '.join(p.name for p in providers)} over {len(tickers)} assets{note} — "
        f"{'best portfolio (objective) wins; time shown' if by_quality else 'fastest feasible time wins'}\n",
        flush=True,
    )

    def dispatch(provider):
        if provider.name == "gurobi":
            return provider.solve_qp(problem, config.SOLVER_DEADLINE_S)
        return provider.solve_qubo(qubo, problem, config.SOLVER_DEADLINE_S)

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
            feas = check_feasibility(
                solution.weights, problem.w_max, problem.w_min, cardinality_k=problem.cardinality_k
            )
            solution.feasible = feas.feasible
            _print_solution(provider.name, provider.role, solution, feas, tickers)
            results.append(solution)

    feasible = [solution for solution in results if solution.feasible]
    winner = pick_winner(feasible)
    if winner is None:
        print("\nno feasible solution from any solver")
        return
    basis = "best portfolio" if by_quality else "solve/access time"
    print(
        f"\nwinner by {basis}: {winner.provider} ({winner.provider_role})  obj={winner.objective:.5f}"
    )
    _print_speedup(winner, results, winner.provider)


def cmd_verify_dwave(args: argparse.Namespace) -> None:
    """Submit one small QUBO to Leap and report solver, embedding, and timing."""
    from .financial.prices.source import set_source
    from .financial.prices.synthetic import SyntheticMarketSource
    from .solvers.providers import dwave
    from .solvers.sampling import select_solution

    if not dwave.is_configured():
        parser_error = "DWAVE_API_TOKEN is not set — export it and rerun"
        raise SystemExit(parser_error)

    set_source(SyntheticMarketSource())  # verification targets Leap, not market data
    tickers = _basket(args)
    problem = _build_problem(tickers, args)
    qubo = encode_qubo(problem)
    print(f"problem: {len(tickers)} assets → {qubo.n}-variable QUBO (dense)", flush=True)

    from dwave.system import DWaveCliqueSampler

    sampler = DWaveCliqueSampler()
    qpu = getattr(sampler, "qpu", None)
    chip = (
        getattr(qpu, "properties", {}).get("chip_id")
        or sampler.properties.get("chip_id")
        or sampler.properties.get("qpu_properties", {}).get("chip_id", "?")
    )
    clique_cap = getattr(sampler, "largest_clique_size", "?")
    print(f"solver:  {chip}  (largest clique capacity: {clique_cap})", flush=True)
    print(
        f"params:  anneal {config.DWAVE_ANNEAL_TIME_US} µs · chain-strength UTC ×"
        f"{config.DWAVE_CHAIN_STRENGTH_PREFACTOR} · {config.DWAVE_NUM_READS} reads (parity with SA)",
        flush=True,
    )

    response = sampler.sample_qubo(
        qubo.to_dict(),
        label="qtw-verify-dwave",
        return_embedding=True,
        **dwave.sample_kwargs(config.DWAVE_NUM_READS),
    )

    context = response.info.get("embedding_context", {})
    embedding = context.get("embedding", {})
    if embedding:
        lengths = [len(chain) for chain in embedding.values()]
        print(
            f"embedding: {len(embedding)} logical vars → {sum(lengths)} physical qubits  "
            f"(chain length min/avg/max: {min(lengths)}/{sum(lengths) / len(lengths):.1f}/{max(lengths)})"
        )
    if context.get("chain_strength") is not None:
        print(f"chain strength: {float(context['chain_strength']):.4f}")
    record = getattr(response, "record", None)
    if record is not None and "chain_break_fraction" in record.dtype.names:
        cbf = record.chain_break_fraction
        print(f"chain breaks: mean {cbf.mean() * 100:.2f}%  max {cbf.max() * 100:.2f}%")

    timing = response.info.get("timing", {})
    for key in (
        "qpu_access_time",
        "qpu_programming_time",
        "qpu_anneal_time_per_sample",
        "qpu_readout_time_per_sample",
    ):
        if key in timing:
            print(f"{key}: {timing[key]} µs")

    weights, _ = select_solution(response, qubo, problem)
    feas = check_feasibility(
        weights, problem.w_max, problem.w_min, cardinality_k=problem.cardinality_k
    )
    print(
        f"\nbest read: Σw={weights.sum():.4f}  feasible={feas.feasible}"
        + ("" if feas.feasible else f"  ({feas.reason})")
    )

    # Objective spread across feasible reads — if the QPU 'sees' the objective,
    # the best feasible read beats the mean; identical values mean it's only
    # satisfying constraints and the spread is random.
    from .financial.projection import select_weights
    from .financial.qubo_decoder import decode_bitstring

    # The "select" encoding decodes via greedy-project + QP (not the bit→weight decoder, which
    # has no select branch and would silently misread the selection bits as convex weights).
    is_select = qubo.decode_meta.scheme == "select"
    rho = correlation_matrix(problem.Sigma) if (is_select and problem.frustration_beta) else None
    objectives = []
    for sample in response.samples():
        bits = np.array([sample[i] for i in range(qubo.n)], dtype=np.int8)
        w = (
            select_weights(bits, problem, rho)
            if is_select
            else decode_bitstring(bits, qubo.decode_meta, normalize=True)
        )
        if check_feasibility(
            w, problem.w_max, problem.w_min, cardinality_k=problem.cardinality_k
        ).feasible:
            objectives.append(problem.objective(w))
    if objectives:
        print(
            f"feasible reads: {len(objectives)}/{config.DWAVE_NUM_READS}  "
            f"objective best/mean: {min(objectives):.6f} / {sum(objectives) / len(objectives):.6f}"
        )


def _print_speedup(winner, results, winner_label) -> None:
    if winner is None or winner.solve_time_s <= 0:
        return
    classical = [s for s in results if s is not winner and s.provider_role == "CPU"]
    classical = [s for s in classical if s.solve_time_s and s.solve_time_s > 0]
    if not classical:
        return
    # Compare to the FASTEST classical (the toughest, most honest comparison). The quality
    # winner can be SLOWER than classical — report the time relationship in the right direction.
    other = min(classical, key=lambda s: s.solve_time_s)
    ratio = other.solve_time_s / winner.solve_time_s
    if ratio >= 1.05:
        print(f"\nwinner {winner_label} solved ~{ratio:.0f}× faster than {other.provider}")
    elif ratio <= 0.95:
        print(
            f"\nwinner {winner_label} took ~{1 / ratio:.0f}× longer than {other.provider} "
            f"but found the better portfolio"
        )
    else:
        print(f"\nwinner {winner_label} and {other.provider} solved in ~the same time")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rebalance", type=int, default=50, help="rebalance frequency 0–100")
    parser.add_argument("--risk", type=int, default=50, help="risk preference 0–100")
    parser.add_argument("--max-position", type=int, default=50, help="max position size 0–100")
    parser.add_argument(
        "--hold-count", type=int, default=None, help="Method 3: number of assets to hold (K)"
    )
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

    p_verify = sub.add_parser(
        "verify-dwave", help="submit one QUBO to Leap; report embedding + timing"
    )
    _add_common_args(p_verify)
    p_verify.set_defaults(func=cmd_verify_dwave)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
    except AssetsApiError as exc:
        parser.error(f"{exc}\n(start assets-api, or run with MARKET_DATA_SOURCE=synthetic)")


if __name__ == "__main__":
    main()
