"""Parallel solver race — first feasible solution wins.

Every provider receives the identical optimization problem: Gurobi natively as
an MIQP, D-Wave/SA as the bit-discretized QUBO encoded from it. They run
concurrently in a thread pool — the heavy solve work (Gurobi's C core, neal's
sampler) releases the GIL, so threads give real parallelism here.

The first solver to return a *feasible* solution wins the job. The remaining
results are still collected: for the per-Q-hash audit log, and to provide the
classical wall-clock baseline for the vsClassical comparison (decision Q7).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .. import config
from ..financial.qubo_encoder import encode_qubo, qubo_hash
from ..financial.types import MIQPProblem
from .feasibility import check_feasibility
from .providers.gurobi import GurobiProvider
from .providers.sa import SAProvider
from .types import QuboMatrix, Solution, SolverFailed


@dataclass
class RaceResult:
    """Outcome of one solver race."""

    winner: Solution
    runner_up_classical: Solution | None  # classical baseline for vsClassical
    all_results: list[Solution]  # every solution that finished, for the audit log
    q_hash: str  # SHA-256 of the QUBO matrix raced on

    @property
    def vs_classical(self) -> float:
        """Winner wall-clock relative to the best classical runner-up (Q7).

        Defined as winner_solve_time / runner_up_classical_solve_time. With no
        classical runner-up (only one solver finished), defaults to 1.0.
        """
        if self.runner_up_classical is None:
            return 1.0
        runner_time = self.runner_up_classical.solve_time_s
        if runner_time <= 0.0:
            return 1.0
        return self.winner.solve_time_s / runner_time


def _dispatch(provider: object, miqp: MIQPProblem, qubo: QuboMatrix, deadline_s: float) -> Solution:
    """Call the provider on whichever problem form it consumes."""
    if provider.name == "gurobi":  # type: ignore[attr-defined]
        return provider.solve_miqp(miqp, deadline_s)  # type: ignore[attr-defined]
    return provider.solve_qubo(qubo, miqp, deadline_s)  # type: ignore[attr-defined]


def race(miqp: MIQPProblem, deadline_s: float | None = None) -> RaceResult:
    """Run the solver race; return the first feasible solution as the winner.

    Raises SolverFailed if no provider returns a feasible solution before the
    overall race deadline.
    """
    overall_deadline = deadline_s if deadline_s is not None else config.RACE_OVERALL_DEADLINE_S
    per_solver_deadline = config.SOLVER_DEADLINE_S

    qubo = encode_qubo(miqp)
    q_h = qubo_hash(qubo)

    # D-Wave joins the race later; until then the field is Gurobi + SA.
    providers = [GurobiProvider(), SAProvider()]

    results: list[Solution] = []
    winner: Solution | None = None

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(_dispatch, p, miqp, qubo, per_solver_deadline): p.name
            for p in providers
        }
        try:
            for future in as_completed(futures, timeout=overall_deadline):
                try:
                    solution = future.result()
                except SolverFailed:
                    continue  # provider unavailable or produced nothing usable
                feasibility = check_feasibility(solution.weights, miqp.K, miqp.w_max)
                solution.feasible = feasibility.feasible
                results.append(solution)
                if solution.feasible and winner is None:
                    winner = solution
                    # Keep collecting — the runner-up gives us the vsClassical baseline.
        except TimeoutError:
            # Overall deadline hit; proceed with whatever finished in time.
            pass

    if winner is None:
        raise SolverFailed("no feasible solution from any provider before deadline")

    runner_up_classical = _pick_runner_up_classical(winner, results)
    return RaceResult(
        winner=winner,
        runner_up_classical=runner_up_classical,
        all_results=results,
        q_hash=q_h,
    )


def _pick_runner_up_classical(winner: Solution, results: list[Solution]) -> Solution | None:
    """Fastest classical (CPU-role) solution that isn't the winner.

    Prefers feasible runner-ups so the vsClassical baseline reflects a real
    classical solve, but falls back to any other CPU result rather than dropping
    the comparison entirely.
    """
    others = [s for s in results if s is not winner and s.provider_role == "CPU"]
    if not others:
        return None
    feasible = [s for s in others if s.feasible]
    pool = feasible if feasible else others
    return min(pool, key=lambda s: s.solve_time_s)
