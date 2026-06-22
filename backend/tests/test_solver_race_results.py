from __future__ import annotations

import numpy as np

from backend import config
from backend.solvers import router
from backend.solvers.types import Solution, SolverFailed


class FakeProvider:
    role = "CPU"

    def __init__(
        self,
        name: str,
        weights: list[float] | None,
        *,
        fail: bool = False,
        solve_time_s: float = 0.12,
    ) -> None:
        self.name = name
        self._weights = weights
        self._fail = fail
        self._solve_time_s = solve_time_s

    def solve_qubo(self, qubo, problem, deadline_s):
        if self._fail:
            raise SolverFailed("planned failure")
        weights = np.array(self._weights, dtype=float)
        return Solution(
            weights=weights,
            objective=problem.objective(weights),
            solve_time_s=self._solve_time_s,
            provider=self.name,
            provider_role=self.role,
            feasible=False,
        )


def test_race_keeps_winner_infeasible_and_failed_solver_rows(
    monkeypatch, synthetic_problem_3assets
):
    monkeypatch.setattr(
        router,
        "build_providers",
        lambda include_qpu=True: [
            FakeProvider("winner", [1 / 3, 1 / 3, 1 / 3]),
            FakeProvider("bad", [1.0, 0.0, 0.0]),
            FakeProvider("failed", None, fail=True),
        ],
    )

    result = router.race(synthetic_problem_3assets, deadline_s=2.0)

    assert result.winner.provider == "winner"
    by_provider = {run.provider: run for run in result.solver_runs}
    assert by_provider["winner"].status == "winner"
    assert by_provider["winner"].feasible is True
    assert by_provider["bad"].status == "infeasible"
    assert by_provider["bad"].feasible is False
    assert by_provider["failed"].status == "failed"
    assert by_provider["failed"].error == "planned failure"


def test_race_winner_is_fastest_feasible_solve_time(monkeypatch, synthetic_problem_3assets):
    monkeypatch.setattr(config, "RACE_WINNER_BY", "speed")  # legacy fastest-feasible mode
    monkeypatch.setattr(
        router,
        "build_providers",
        lambda include_qpu=True: [
            FakeProvider("slow", [1 / 3, 1 / 3, 1 / 3], solve_time_s=0.5),
            FakeProvider("fast", [0.2, 0.4, 0.4], solve_time_s=0.1),
        ],
    )

    result = router.race(synthetic_problem_3assets, deadline_s=2.0)

    assert result.winner.provider == "fast"
    by_provider = {run.provider: run for run in result.solver_runs}
    assert by_provider["fast"].status == "winner"
    assert by_provider["slow"].status == "feasible"


def test_best_objective_marked_separately_from_speed_winner(monkeypatch, synthetic_problem_3assets):
    # Winner = fastest feasible; best_objective = lowest-objective feasible. They are
    # independent flags (the quality leader may not be the speed winner).
    monkeypatch.setattr(config, "RACE_WINNER_BY", "speed")  # legacy fastest-feasible mode
    monkeypatch.setattr(
        router,
        "build_providers",
        lambda include_qpu=True: [
            FakeProvider("fast", [1 / 3, 1 / 3, 1 / 3], solve_time_s=0.1),
            FakeProvider("slow", [0.2, 0.4, 0.4], solve_time_s=0.5),
        ],
    )

    result = router.race(synthetic_problem_3assets, deadline_s=2.0)
    by_provider = {run.provider: run for run in result.solver_runs}

    # winner is always the fastest feasible, independent of objective
    assert result.winner.provider == "fast"
    assert by_provider["fast"].status == "winner"

    # exactly one best_objective flag, on the lowest-objective feasible solver
    objs = {s.provider: s.objective for s in result.all_results if s.feasible}
    best_provider = min(objs, key=objs.get)
    assert by_provider[best_provider].best_objective is True
    assert sum(1 for run in result.solver_runs if run.best_objective) == 1


def test_objective_winner_prefers_best_portfolio_over_speed(monkeypatch, synthetic_problem_3assets):
    # RACE_WINNER_BY="objective" (booth default): the better PORTFOLIO wins even when slower;
    # an equal-quality tie falls back to the faster solver.
    monkeypatch.setattr(config, "RACE_WINNER_BY", "objective")

    w_a, w_b = [0.2, 0.4, 0.4], [1 / 3, 1 / 3, 1 / 3]
    o_a = synthetic_problem_3assets.objective(np.array(w_a))
    o_b = synthetic_problem_3assets.objective(np.array(w_b))
    better, worse = (w_a, w_b) if o_a < o_b else (w_b, w_a)

    monkeypatch.setattr(
        router,
        "build_providers",
        lambda include_qpu=True: [
            FakeProvider("slow_best", better, solve_time_s=0.5),
            FakeProvider("fast_worse", worse, solve_time_s=0.1),
        ],
    )
    result = router.race(synthetic_problem_3assets, deadline_s=2.0)
    assert result.winner.provider == "slow_best"  # quality wins despite being slower
    # The best_objective badge coincides with the winner in objective mode (UI coherence).
    by_provider = {run.provider: run for run in result.solver_runs}
    assert by_provider["slow_best"].best_objective is True
    assert sum(1 for run in result.solver_runs if run.best_objective) == 1

    # Identical portfolios → quality tie → faster wins.
    monkeypatch.setattr(
        router,
        "build_providers",
        lambda include_qpu=True: [
            FakeProvider("slow_tie", worse, solve_time_s=0.5),
            FakeProvider("fast_tie", worse, solve_time_s=0.1),
        ],
    )
    result = router.race(synthetic_problem_3assets, deadline_s=2.0)
    assert result.winner.provider == "fast_tie"
