"""End-to-end solver checks on synthetic data.

These exercise the real solvers and are skipped when the optional backends
aren't installed. The SA-vs-Gurobi agreement test is the canary the handoff
calls out: if SA can't reach a feasible solution close to Gurobi's optimum, the
QUBO penalty weights are too low for this μ/Σ regime.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from backend.financial.qubo_encoder import encode_qubo
from backend.solvers.feasibility import check_feasibility

_HAS_GUROBI = importlib.util.find_spec("gurobipy") is not None
_HAS_NEAL = importlib.util.find_spec("neal") is not None

requires_gurobi = pytest.mark.skipif(not _HAS_GUROBI, reason="gurobipy not installed")
requires_neal = pytest.mark.skipif(not _HAS_NEAL, reason="dwave-neal not installed")


def _mean_variance_objective(weights: np.ndarray, miqp) -> float:
    risk = 0.5 * miqp.gamma * weights @ miqp.Sigma @ weights
    ret = miqp.mu @ weights
    return float(risk - ret)


@requires_gurobi
def test_gurobi_returns_feasible_solution(synthetic_miqp_3assets):
    from backend.solvers.providers.gurobi import GurobiProvider

    solution = GurobiProvider().solve_miqp(synthetic_miqp_3assets, deadline_s=5.0)
    result = check_feasibility(
        solution.weights, synthetic_miqp_3assets.K, synthetic_miqp_3assets.w_max
    )
    assert result.feasible, result.reason


@requires_neal
def test_sa_returns_feasible_solution(synthetic_miqp_3assets):
    from backend.solvers.providers.sa import SAProvider

    qubo = encode_qubo(synthetic_miqp_3assets)
    solution = SAProvider().solve_qubo(qubo, synthetic_miqp_3assets, deadline_s=5.0)
    result = check_feasibility(
        solution.weights, synthetic_miqp_3assets.K, synthetic_miqp_3assets.w_max
    )
    assert result.feasible, f"SA infeasible — raise penalty weights ({result.reason})"


@requires_gurobi
@requires_neal
def test_sa_objective_is_close_to_gurobi(synthetic_miqp_3assets):
    from backend.solvers.providers.gurobi import GurobiProvider
    from backend.solvers.providers.sa import SAProvider

    gurobi = GurobiProvider().solve_miqp(synthetic_miqp_3assets, deadline_s=5.0)
    qubo = encode_qubo(synthetic_miqp_3assets)
    sa = SAProvider().solve_qubo(qubo, synthetic_miqp_3assets, deadline_s=5.0)

    # SA solves on a discretized grid, so its true objective can only be ≥
    # Gurobi's continuous optimum, up to the bit-granularity gap.
    gurobi_obj = _mean_variance_objective(gurobi.weights, synthetic_miqp_3assets)
    sa_obj = _mean_variance_objective(sa.weights, synthetic_miqp_3assets)
    assert sa_obj >= gurobi_obj - 1e-6
    assert sa_obj == pytest.approx(gurobi_obj, abs=0.02)


@requires_gurobi
def test_router_race_produces_a_feasible_winner(synthetic_miqp_3assets):
    from backend.solvers.router import race

    result = race(synthetic_miqp_3assets, deadline_s=10.0)
    assert result.winner.feasible
    assert result.winner.provider in ("gurobi", "sa")
    assert len(result.q_hash) == 64
    assert result.vs_classical > 0.0
