"""QUBO encoder: shape, symmetry, hashing."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.qubo_encoder import encode_qubo, qubo_hash
from backend.financial.types import PortfolioProblem


def _zero_linear_problem(n: int, gamma: float, w_min: float, w_max: float) -> PortfolioProblem:
    """Problem whose linear objective term vanishes (μ = γ·Σ·m, m = w_min·1), so
    Q(pmult=0) is exactly A_obj and the off-diagonal of Q(P)−Q(0) is exactly the
    budget block — letting a test read both coefficient peaks directly."""
    sigma = np.eye(n)
    mu = gamma * (sigma @ np.full(n, w_min))
    return PortfolioProblem(
        mu=mu,
        Sigma=sigma,
        gamma=gamma,
        w_max=w_max,
        w_min=w_min,
        asset_tickers=[f"A{i}" for i in range(n)],
    )


def test_shape_and_symmetry(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets, bits_per_asset=4)
    assert qubo.Q.shape == (12, 12)  # N=3 × b=4, no indicator block
    assert np.allclose(qubo.Q, qubo.Q.T)


def test_hash_is_stable_and_content_addressed(synthetic_problem_3assets):
    a = encode_qubo(synthetic_problem_3assets)
    b = encode_qubo(synthetic_problem_3assets)
    assert qubo_hash(a) == qubo_hash(b)

    synthetic_problem_3assets.gamma = 5.0
    c = encode_qubo(synthetic_problem_3assets)
    assert qubo_hash(a) != qubo_hash(c)


def test_higher_bit_precision_grows_the_matrix(synthetic_problem_3assets):
    q4 = encode_qubo(synthetic_problem_3assets, bits_per_asset=4)
    q5 = encode_qubo(synthetic_problem_3assets, bits_per_asset=5)
    assert q5.n == q4.n + 3  # one extra bit per asset


def test_budget_penalty_ratio_is_config_invariant():
    # pmult is now the penalty:objective PEAK-COEFFICIENT ratio, the same for any
    # basket size / bit depth / w_max. (Old un-normalized λ_sum gave a ratio of
    # pmult·u_max², which differs wildly between these two configs.)
    p_mult = 7.0
    configs = [
        dict(n=4, gamma=3.0, w_min=0.05, w_max=0.40, b=4),  # small basket, high w_max
        dict(n=25, gamma=3.0, w_min=0.01, w_max=0.041, b=3),  # full basket, low w_max
    ]
    ratios = []
    for cfg in configs:
        prob = _zero_linear_problem(cfg["n"], cfg["gamma"], cfg["w_min"], cfg["w_max"])
        q0 = encode_qubo(prob, bits_per_asset=cfg["b"], penalty_mult_budget=0.0).Q
        qp = encode_qubo(prob, bits_per_asset=cfg["b"], penalty_mult_budget=p_mult).Q
        obj_peak = float(np.abs(q0).max())  # = max|A_obj| (b_obj = 0)
        budget = qp - q0
        np.fill_diagonal(budget, 0.0)  # strip the folded linear budget term
        bud_peak = float(np.abs(budget).max())  # = max|A_budget| off-diagonal
        ratios.append(bud_peak / obj_peak)

    for ratio in ratios:
        assert ratio == pytest.approx(p_mult, rel=1e-9)


def test_large_baskets_drop_to_2_bits(synthetic_problem_3assets):
    from backend.financial.qubo_encoder import bits_for_basket

    # Large baskets skip straight from b=4 to b=2 (hardware: b=3 is feasibility-
    # dominated by b=2 at the same basket — fewer variables wins). See config.
    assert bits_for_basket(6) == 4
    assert bits_for_basket(15) == 4
    assert bits_for_basket(16) == 2
    assert bits_for_basket(25) == 2
    # small fixture still encodes at full precision
    assert encode_qubo(synthetic_problem_3assets).n == 12
