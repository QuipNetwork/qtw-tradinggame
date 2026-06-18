"""Parallel solver race — fastest feasible solve/access time wins.

Each provider gets the problem in its native form: Gurobi the continuous QP,
SA/D-Wave the bit-discretized QUBO. The solve work releases the GIL, so a
thread pool gives real parallelism. All results are kept for the audit log
and the solver comparison display.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Literal

from .. import config
from ..financial.qubo_encoder import encode_qubo, qubo_hash
from ..financial.types import PortfolioProblem
from .feasibility import check_feasibility
from .providers import dwave
from .providers.gurobi import GurobiProvider
from .providers.sa import SAProvider
from .types import QuboMatrix, Solution, SolverFailed

SolverStatus = Literal["winner", "feasible", "infeasible", "failed", "timeout"]


@dataclass
class SolverRun:
    provider: str
    provider_role: str
    status: SolverStatus
    feasible: bool
    solve_time_s: float | None
    race_time_s: float | None
    objective: float | None
    error: str | None = None


@dataclass
class RaceResult:
    winner: Solution
    runner_up_classical: Solution | None
    all_results: list[Solution]
    solver_runs: list[SolverRun]
    q_hash: str

    @property
    def vs_classical(self) -> float:
        """Legacy multiplier against the classical runner-up.

        The frontend now renders percentage margin from solver_results; this is
        retained for older clients and cached mock responses.
        """
        if self.runner_up_classical is None or self.winner.solve_time_s <= 0.0:
            return 1.0
        return self.runner_up_classical.solve_time_s / self.winner.solve_time_s


def build_providers(*, include_qpu: bool = True) -> list:
    """The race field: SA always, Gurobi unless disabled for production,
    the D-Wave QPU when a Leap token is set."""
    providers: list = [GurobiProvider()] if config.GUROBI_IN_RACE else []
    providers.append(SAProvider())
    if include_qpu and dwave.is_configured():
        providers.append(dwave.DWaveProvider())
    return providers


def _dispatch(provider: object, problem: PortfolioProblem, qubo: QuboMatrix, deadline_s: float):
    started = time.perf_counter()
    if provider.name == "gurobi":  # type: ignore[attr-defined]
        solution = provider.solve_qp(problem, deadline_s)  # type: ignore[attr-defined]
    else:
        solution = provider.solve_qubo(qubo, problem, deadline_s)  # type: ignore[attr-defined]
    return solution, time.perf_counter() - started


def race(
    problem: PortfolioProblem,
    deadline_s: float | None = None,
    *,
    include_qpu: bool = True,
) -> RaceResult:
    """Run the race; raise SolverFailed if nothing feasible arrives in time."""
    overall_deadline = deadline_s if deadline_s is not None else config.RACE_OVERALL_DEADLINE_S
    per_solver_deadline = config.SOLVER_DEADLINE_S

    qubo = encode_qubo(problem)
    q_h = qubo_hash(qubo)
    providers = build_providers(include_qpu=include_qpu)

    results: list[Solution] = []
    solver_runs: list[SolverRun] = []
    winner: Solution | None = None

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(_dispatch, p, problem, qubo, per_solver_deadline): p.name
            for p in providers
        }
        try:
            for future in as_completed(futures, timeout=overall_deadline):
                try:
                    solution, race_time_s = future.result()
                except SolverFailed as exc:
                    provider = next(p for p in providers if p.name == futures[future])
                    solver_runs.append(
                        SolverRun(
                            provider=provider.name,
                            provider_role=provider.role,
                            status="failed",
                            feasible=False,
                            solve_time_s=None,
                            race_time_s=None,
                            objective=None,
                            error=str(exc),
                        )
                    )
                    continue
                feas = check_feasibility(solution.weights, problem.w_max, problem.w_min)
                solution.feasible = feas.feasible
                results.append(solution)
                solver_runs.append(
                    SolverRun(
                        provider=solution.provider,
                        provider_role=solution.provider_role,
                        status="feasible" if solution.feasible else "infeasible",
                        feasible=solution.feasible,
                        solve_time_s=solution.solve_time_s,
                        race_time_s=race_time_s,
                        objective=solution.objective,
                    )
                )
        except TimeoutError:
            pass  # deadline hit; proceed with whatever finished

        finished = set(futures) - {f for f in futures if not f.done()}
        timed_out_provider_names = {
            futures[future] for future in futures if future not in finished
        }
        seen_provider_names = {run.provider for run in solver_runs}
        for provider in providers:
            if provider.name in timed_out_provider_names and provider.name not in seen_provider_names:
                solver_runs.append(
                    SolverRun(
                        provider=provider.name,
                        provider_role=provider.role,
                        status="timeout",
                        feasible=False,
                        solve_time_s=None,
                        race_time_s=overall_deadline,
                        objective=None,
                    )
                )

    feasible_results = [solution for solution in results if solution.feasible]
    winner = min(feasible_results, key=lambda solution: solution.solve_time_s, default=None)
    if winner is None:
        raise SolverFailed("no feasible solution from any provider before deadline")

    for run in solver_runs:
        if run.provider == winner.provider:
            run.status = "winner"
            break

    return RaceResult(
        winner=winner,
        runner_up_classical=_pick_runner_up_classical(winner, results),
        all_results=results,
        solver_runs=solver_runs,
        q_hash=q_h,
    )


def _pick_runner_up_classical(winner: Solution, results: list[Solution]) -> Solution | None:
    """Fastest classical (CPU) solution that isn't the winner, preferring feasible ones."""
    others = [s for s in results if s is not winner and s.provider_role == "CPU"]
    if not others:
        return None
    feasible = [s for s in others if s.feasible]
    return min(feasible or others, key=lambda s: s.solve_time_s)
