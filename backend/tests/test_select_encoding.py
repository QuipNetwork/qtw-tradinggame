"""C2 penalty-free selection encoding: encode_select, greedy_project, and the select solve path."""

from __future__ import annotations

import numpy as np
import pytest

from backend import config
from backend.financial.projection import greedy_project
from backend.financial.qubo_encoder import encode_qubo, encode_select
from backend.financial.types import PortfolioProblem, correlation_matrix
from backend.solvers.feasibility import check_feasibility
from backend.solvers.sampling import select_solution


def _problem(beta: float = 0.0) -> PortfolioProblem:
    rng = np.random.default_rng(0)
    n = 6
    A = rng.normal(size=(n, n))
    Sigma = A @ A.T / n + np.eye(n) * 0.02  # SPD covariance
    return PortfolioProblem(
        mu=rng.uniform(0.0, 0.05, size=n),
        Sigma=Sigma,
        gamma=2.0,
        w_max=0.6,
        w_min=1 / 8,
        asset_tickers=[f"A{i}" for i in range(n)],
        cardinality_k=3,
        n_units_M=8,
        u_min_units=1,
        frustration_beta=beta,
    )


class _FakeResp:
    """Minimal stand-in for a SampleSet: .samples() yields dict reads."""

    def __init__(self, samples):
        self._samples = samples

    def samples(self):
        return self._samples


def test_encode_select_is_selection_only(monkeypatch):
    monkeypatch.setattr(config, "CARDINALITY_ENCODING", "select")
    p = _problem()
    qubo = encode_qubo(p)

    assert qubo.decode_meta.scheme == "select"
    assert qubo.n == p.N  # one bit per asset, no weight bits
    assert np.allclose(qubo.Q, qubo.Q.T)

    k, g = p.cardinality_k, p.gamma
    coef = g / (2.0 * k * k)
    for i in range(p.N):
        assert qubo.Q[i, i] == pytest.approx(-p.mu[i] / k + coef * p.Sigma[i, i])
        for j in range(i + 1, p.N):
            assert qubo.Q[i, j] == pytest.approx(coef * p.Sigma[i, j])


def test_encode_select_beta_adds_correlation_coupling():
    b = 1e-3
    q0 = encode_select(_problem(beta=0.0))
    qb = encode_select(_problem(beta=b))
    rho = correlation_matrix(_problem().Sigma)
    n = q0.n
    for i in range(n):
        for j in range(i + 1, n):
            assert qb.Q[i, j] - q0.Q[i, j] == pytest.approx(0.5 * b * rho[i, j])


def test_greedy_project_repairs_to_exactly_k():
    p = _problem()
    # too many selected (5 of 6) → trims to K; too few (1) → grows to K; none → grows to K
    for raw in ([1, 1, 1, 1, 1, 0], [1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]):
        support = greedy_project(np.array(raw, dtype=np.int8), p)
        assert len(support) == p.cardinality_k
        assert set(support).issubset(range(p.N))


def test_greedy_project_matches_exact_best_k_on_small_case():
    from itertools import combinations

    p = _problem()
    rho = None
    # exact best-K by the same subset value the projector uses
    from backend.financial.projection import _subset_value

    raw = np.ones(p.N, dtype=np.int8)  # all selected → projector must trim to the best K
    greedy = greedy_project(raw, p)
    exact = min(
        combinations(range(p.N), p.cardinality_k), key=lambda s: _subset_value(set(s), p, rho)
    )
    assert _subset_value(set(greedy), p, rho) == pytest.approx(_subset_value(set(exact), p, rho))


def test_select_solution_projects_weights_and_is_feasible(monkeypatch):
    monkeypatch.setattr(config, "CARDINALITY_ENCODING", "select")
    p = _problem()
    qubo = encode_qubo(p)
    # a read selecting 4 assets when K=3 → projector trims, QP sets weights
    sample = {0: 1, 1: 1, 2: 1, 3: 1, 4: 0, 5: 0}
    weights, bits = select_solution(_FakeResp([sample]), qubo, p)

    assert weights.sum() == pytest.approx(1.0)
    assert int((weights > 1e-9).sum()) == p.cardinality_k  # exactly K held
    feas = check_feasibility(weights, p.w_max, p.w_min, cardinality_k=p.cardinality_k)
    assert feas.feasible


def test_select_beta_changes_objective_scoring(monkeypatch):
    # With β>0 the same support is scored with the diversification term (objective() includes it),
    # so the select path optimizes the β-augmented objective.
    monkeypatch.setattr(config, "CARDINALITY_ENCODING", "select")
    p = _problem(beta=1e-3)
    qubo = encode_qubo(p)
    sample = {0: 1, 1: 1, 2: 1, 3: 0, 4: 0, 5: 0}
    weights, _ = select_solution(_FakeResp([sample]), qubo, p)
    held = (weights > 1e-9).astype(float)
    rho = correlation_matrix(p.Sigma)
    pair = 0.5 * (held @ rho @ held - held.sum())
    mv = 0.5 * p.gamma * weights @ p.Sigma @ weights - p.mu @ weights
    assert p.objective(weights) == pytest.approx(mv + p.frustration_beta * pair)
