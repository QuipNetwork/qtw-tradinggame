"""QUBO encoder: shape, symmetry, hashing."""

from __future__ import annotations

import numpy as np
import pytest

from backend import config
from backend.financial.qubo_encoder import (
    encode_method3,
    encode_qubo,
    qubo_hash,
    units_for_cardinality,
)
from backend.financial.types import PortfolioProblem


def _method3_problem(n: int, k: int, gamma: float = 3.0) -> PortfolioProblem:
    m = units_for_cardinality(k)  # production grid: smallest power of two ≥ K
    return PortfolioProblem(
        mu=np.full(n, 0.05),
        Sigma=np.eye(n),
        gamma=gamma,
        w_max=0.5,
        w_min=config.METHOD3_U_MIN / m,
        asset_tickers=[f"A{i}" for i in range(n)],
        cardinality_k=k,
        n_units_M=m,
        u_min_units=config.METHOD3_U_MIN,
    )


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


def test_method3_shape_symmetry_and_scheme():
    prob = _method3_problem(5, 3)
    b = prob.n_units_M.bit_length() - 2  # b = log2(M) − 1
    q = encode_method3(prob)
    assert q.Q.shape == (5 * (1 + b), 5 * (1 + b))  # n select + n·b increment bits
    assert np.allclose(q.Q, q.Q.T)
    assert q.decode_meta.scheme == "method3"
    assert q.decode_meta.n_total_bits == 5 * (1 + b)


def test_method3_dispatch_via_encode_qubo():
    # encode_qubo routes cardinality problems to the Method 3 encoder
    q = encode_qubo(_method3_problem(5, 3))
    assert q.decode_meta.scheme == "method3"


def test_method3_hash_is_content_addressed():
    a = encode_method3(_method3_problem(6, 4))
    assert qubo_hash(a) == qubo_hash(encode_method3(_method3_problem(6, 4)))
    assert qubo_hash(a) != qubo_hash(encode_method3(_method3_problem(6, 3)))  # k changes it


def test_units_for_cardinality_minimizes_grid():
    # smallest power of two ≥ K, floored at MIN_UNITS, capped at MAX_UNITS
    assert units_for_cardinality(3) == 8  # floored
    assert units_for_cardinality(8) == 8
    assert units_for_cardinality(9) == 16
    assert units_for_cardinality(16) == 16
    assert units_for_cardinality(17) == 32
    assert units_for_cardinality(28) == 32  # capped (and ≥ universe)
    # invariant: M ≥ K (units must fit the held count) and M is a power of two
    for k in range(2, 29):
        m = units_for_cardinality(k)
        assert m >= k and (m & (m - 1)) == 0


def test_method3_grid_shrinks_vars_for_small_k():
    # small K → small M → fewer variables (the QPU-feasibility lever)
    small_k = encode_method3(_method3_problem(20, 4))  # K=4 → M=8 (b=2) → 3N
    large_k = encode_method3(_method3_problem(20, 20))  # K=20 → M=32 (b=4) → 5N
    assert small_k.n == 20 * 3
    assert large_k.n == 20 * 5
    assert small_k.n < large_k.n


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
