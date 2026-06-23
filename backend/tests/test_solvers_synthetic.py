"""End-to-end solver checks on synthetic data (skipped without the backends)."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from backend.financial.qubo_encoder import encode_qubo
from backend.financial.types import PortfolioProblem
from backend.solvers.feasibility import check_feasibility


def _cardinality_problem_3() -> PortfolioProblem:
    sigma = np.array([[0.04, 0.01, 0.0], [0.01, 0.05, 0.0], [0.0, 0.0, 0.02]])
    return PortfolioProblem(
        mu=np.array([0.03, 0.04, 0.01]),
        Sigma=sigma,
        gamma=2.0,
        w_max=0.6,
        w_min=1 / 32,
        asset_tickers=["A", "B", "C"],
        cardinality_k=2,
        n_units_M=32,
        u_min_units=1,
    )


requires_gurobi = pytest.mark.skipif(
    importlib.util.find_spec("gurobipy") is None, reason="gurobipy not installed"
)
requires_neal = pytest.mark.skipif(
    importlib.util.find_spec("neal") is None, reason="dwave-neal not installed"
)


def _objective(weights: np.ndarray, problem) -> float:
    return float(0.5 * problem.gamma * weights @ problem.Sigma @ weights - problem.mu @ weights)


@requires_gurobi
def test_gurobi_returns_feasible_solution(synthetic_problem_3assets):
    from backend.solvers.providers.gurobi import GurobiProvider

    solution = GurobiProvider().solve_qp(synthetic_problem_3assets, deadline_s=5.0)
    feas = check_feasibility(
        solution.weights, synthetic_problem_3assets.w_max, synthetic_problem_3assets.w_min
    )
    assert feas.feasible, feas.reason


@requires_neal
def test_sa_returns_feasible_solution(synthetic_problem_3assets):
    from backend.solvers.providers.sa import SAProvider

    qubo = encode_qubo(synthetic_problem_3assets)
    solution = SAProvider().solve_qubo(qubo, synthetic_problem_3assets, deadline_s=5.0)
    feas = check_feasibility(
        solution.weights, synthetic_problem_3assets.w_max, synthetic_problem_3assets.w_min
    )
    assert feas.feasible, f"SA infeasible — raise penalty weights ({feas.reason})"


@requires_gurobi
@requires_neal
def test_sa_objective_is_close_to_gurobi(synthetic_problem_3assets):
    from backend.solvers.providers.gurobi import GurobiProvider
    from backend.solvers.providers.sa import SAProvider

    gurobi = GurobiProvider().solve_qp(synthetic_problem_3assets, deadline_s=5.0)
    qubo = encode_qubo(synthetic_problem_3assets)
    sa = SAProvider().solve_qubo(qubo, synthetic_problem_3assets, deadline_s=5.0)

    # SA solves on a discretized grid, so its objective can only be ≥ the
    # continuous optimum, up to grid granularity.
    assert _objective(sa.weights, synthetic_problem_3assets) == pytest.approx(
        _objective(gurobi.weights, synthetic_problem_3assets), abs=0.02
    )


@requires_gurobi
def test_router_race_produces_a_feasible_winner(synthetic_problem_3assets):
    from backend.solvers.router import race

    result = race(synthetic_problem_3assets, deadline_s=10.0)
    assert result.winner.feasible
    assert result.winner.provider in ("gurobi", "sa")
    assert len(result.q_hash) == 64
    assert result.vs_classical > 0.0


@requires_neal
def test_sa_feasible_at_full_universe_scale():
    """Penalty-ratio canary: at 500× (no obj_scale floor) SA must still respect
    the budget on the hardest case — the dense 28-asset, 84-bit QUBO."""

    from backend import config
    from backend.financial.basket import TICKERS
    from backend.financial.estimators.covariance import covariance
    from backend.financial.estimators.expected_return import expected_return
    from backend.financial.prices.source import get_source
    from backend.financial.types import PortfolioProblem
    from backend.solvers.providers.sa import SAProvider

    tickers = list(TICKERS)
    returns = get_source().hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    problem = PortfolioProblem(
        mu=expected_return(returns, config.MU_WINDOW_HOURS),
        Sigma=covariance(returns),
        gamma=1.5,
        w_max=0.27,
        w_min=0.01,
        asset_tickers=tickers,
    )
    qubo = encode_qubo(problem)
    solution = SAProvider().solve_qubo(qubo, problem, deadline_s=10.0)
    feas = check_feasibility(solution.weights, problem.w_max, problem.w_min)
    assert feas.feasible, (
        f"SA infeasible at 500× penalty ratio — raise PENALTY_MULT_BUDGET ({feas.reason})"
    )


# --- cardinality (cardinality + semi-continuous MIQP) ---


@requires_gurobi
def test_cardinality_gurobi_miqp_respects_cardinality():
    from backend.solvers.providers.gurobi import GurobiProvider

    prob = _cardinality_problem_3()
    sol = GurobiProvider().solve_qp(prob, deadline_s=5.0)
    assert int((sol.weights > 1e-6).sum()) == prob.cardinality_k
    feas = check_feasibility(sol.weights, prob.w_max, prob.w_min, cardinality_k=prob.cardinality_k)
    assert feas.feasible, feas.reason


@requires_neal
def test_cardinality_sa_is_cardinality_feasible():
    from backend.solvers.providers.sa import SAProvider

    prob = _cardinality_problem_3()
    sol = SAProvider().solve_qubo(encode_qubo(prob), prob, deadline_s=5.0)
    feas = check_feasibility(sol.weights, prob.w_max, prob.w_min, cardinality_k=prob.cardinality_k)
    assert feas.feasible, f"SA cardinality infeasible ({feas.reason})"


@requires_neal
def test_cardinality_sa_feasible_at_scale():
    """cardinality penalty canary: SA must hit budget + cardinality on the dense
    full-universe selection QUBO (28 assets, k=8, ~140 vars)."""
    from backend import config
    from backend.financial.basket import TICKERS
    from backend.financial.estimators.covariance import covariance
    from backend.financial.estimators.expected_return import expected_return
    from backend.financial.prices.source import get_source
    from backend.solvers.providers.sa import SAProvider

    tickers = list(TICKERS)
    returns = get_source().hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    k = 8
    problem = PortfolioProblem(
        mu=expected_return(returns, config.MU_WINDOW_HOURS),
        Sigma=covariance(returns),
        gamma=1.5,
        w_max=0.3,
        w_min=1 / 32,
        asset_tickers=tickers,
        cardinality_k=k,
        n_units_M=32,
        u_min_units=1,
    )
    sol = SAProvider().solve_qubo(encode_qubo(problem), problem, deadline_s=10.0)
    feas = check_feasibility(sol.weights, problem.w_max, problem.w_min, cardinality_k=k)
    assert feas.feasible, (
        f"cardinality SA infeasible at scale — tune the cardinality penalty multipliers ({feas.reason})"
    )
