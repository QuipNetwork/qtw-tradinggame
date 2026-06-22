"""QUBO encoder: shape, symmetry, hashing."""

from __future__ import annotations

import numpy as np
import pytest

from backend import config
from backend.financial.qubo_encoder import (
    encode_penalized,
    encode_qubo,
    qubo_hash,
    units_for_cardinality,
)
from backend.financial.types import PortfolioProblem


def _cardinality_problem(n: int, k: int, gamma: float = 3.0) -> PortfolioProblem:
    m = units_for_cardinality(k)  # production grid: smallest power of two ≥ K
    return PortfolioProblem(
        mu=np.full(n, 0.05),
        Sigma=np.eye(n),
        gamma=gamma,
        w_max=0.5,
        w_min=config.CARDINALITY_U_MIN / m,
        asset_tickers=[f"A{i}" for i in range(n)],
        cardinality_k=k,
        n_units_M=m,
        u_min_units=config.CARDINALITY_U_MIN,
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


def test_cardinality_shape_symmetry_and_scheme():
    prob = _cardinality_problem(5, 3)
    b = prob.n_units_M.bit_length() - 2  # b = log2(M) − 1
    q = encode_penalized(prob)
    assert q.Q.shape == (5 * (1 + b), 5 * (1 + b))  # n select + n·b increment bits
    assert np.allclose(q.Q, q.Q.T)
    assert q.decode_meta.scheme == "penalized"
    assert q.decode_meta.n_total_bits == 5 * (1 + b)


def test_cardinality_dispatch_via_encode_qubo(monkeypatch):
    # encode_qubo routes cardinality problems to the configured Method-3 encoder
    monkeypatch.setattr(config, "CARDINALITY_ENCODING", "penalized")
    assert encode_qubo(_cardinality_problem(5, 3)).decode_meta.scheme == "penalized"
    monkeypatch.setattr(config, "CARDINALITY_ENCODING", "select")
    assert encode_qubo(_cardinality_problem(5, 3)).decode_meta.scheme == "select"


def test_cardinality_hash_is_content_addressed():
    a = encode_penalized(_cardinality_problem(6, 4))
    assert qubo_hash(a) == qubo_hash(encode_penalized(_cardinality_problem(6, 4)))
    assert qubo_hash(a) != qubo_hash(encode_penalized(_cardinality_problem(6, 3)))  # k changes it


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


def test_units_for_grid_is_size_aware():
    from backend.financial.qubo_encoder import units_for_grid

    # small basket → finest grid (M=32, b=4 ≈ continuous); large basket → coarse (M=8, b=2)
    assert units_for_grid(5, 6) == 32  # 6·log2(32)=30 ≤ 72
    assert units_for_grid(5, 12) == 32  # 12·5=60 ≤ 72
    assert units_for_grid(6, 18) == 16  # 18·5=90 > 72 → step down to b=3 (18·4=72)
    assert units_for_grid(8, 28) == 8  # 28·4=112 > 72 → coarse b=2 (embeddable)
    # K floor always wins when large K needs a bigger grid, even on a large basket
    assert units_for_grid(20, 28) == 32  # K=20 forces M=32 despite the size budget
    # invariants across the universe: power of two, M ≥ K, ≤ MAX_UNITS
    for n in (5, 12, 18, 28):
        for k in range(3, n + 1):
            m = units_for_grid(k, n)
            assert m >= k and (m & (m - 1)) == 0 and m <= config.CARDINALITY_MAX_UNITS


def test_cardinality_grid_shrinks_vars_for_small_k():
    # small K → small M → fewer variables (the QPU-feasibility lever)
    small_k = encode_penalized(_cardinality_problem(20, 4))  # K=4 → M=8 (b=2) → 3N
    large_k = encode_penalized(_cardinality_problem(20, 20))  # K=20 → M=32 (b=4) → 5N
    assert small_k.n == 20 * 3
    assert large_k.n == 20 * 5
    assert small_k.n < large_k.n


def test_increment_place_values_caps_at_w_max():
    from backend.financial.qubo_decoder import decode_bitstring
    from backend.financial.qubo_encoder import increment_place_values

    # Default w_max=0.5 → plain powers of two (no behavior change).
    assert list(increment_place_values(0.5, 8, 1, 2)) == [1.0, 2.0]
    assert list(increment_place_values(0.5, 32, 1, 4)) == [1.0, 2.0, 4.0, 8.0]
    # Tight cap w_max=0.375, M=8 → u_cap=3, so the increment maxes at 2 (units 1..3).
    assert sum(increment_place_values(0.375, 8, 1, 2)) == 2.0

    # The bounded grid never decodes a weight above w_max, even with ALL bits set
    # (the old plain-2^k encoding would have allowed 4/8 = 0.5 > 0.375 here).
    M = 8
    prob = PortfolioProblem(
        mu=np.full(4, 0.05),
        Sigma=np.eye(4),
        gamma=3.0,
        w_max=0.375,
        w_min=1 / M,
        asset_tickers=[f"A{i}" for i in range(4)],
        cardinality_k=3,
        n_units_M=M,
        u_min_units=1,
    )
    q = encode_penalized(prob)
    w = decode_bitstring(np.ones(q.n, dtype=np.int8), q.decode_meta)
    assert w.max() <= prob.w_max + 1e-9


def test_frustration_beta_rewards_diversification():
    from backend.financial.types import PortfolioProblem, correlation_matrix

    # assets 0&1 correlated (+0.8), 0&2 anti-correlated (−0.5)
    Sigma = np.array([[1.0, 0.8, -0.5], [0.8, 1.0, 0.0], [-0.5, 0.0, 1.0]])
    fields = dict(
        mu=np.full(3, 0.05),
        Sigma=Sigma,
        gamma=2.0,
        w_max=0.6,
        w_min=1 / 8,
        asset_tickers=["A", "B", "C"],
        cardinality_k=2,
        n_units_M=8,
        u_min_units=1,
    )
    p0 = PortfolioProblem(**fields, frustration_beta=0.0)
    pb = PortfolioProblem(**fields, frustration_beta=1.0)
    rho = correlation_matrix(Sigma)
    w_corr = np.array([0.5, 0.5, 0.0])  # hold the correlated pair {0,1}
    w_anti = np.array([0.5, 0.0, 0.5])  # hold the anti-correlated pair {0,2}

    # β=0 leaves the objective as plain mean-variance.
    assert p0.objective(w_corr) == pytest.approx(0.5 * 2.0 * (w_corr @ Sigma @ w_corr) - 0.05)
    # β>0 adds exactly β·ρ_ij for the held pair (penalizes +corr, rewards −corr).
    assert pb.objective(w_corr) - p0.objective(w_corr) == pytest.approx(rho[0, 1])  # +0.8
    assert pb.objective(w_anti) - p0.objective(w_anti) == pytest.approx(rho[0, 2])  # −0.5
    # and it changes the QUBO (couples the select bits) — β=0 must be untouched.
    assert not np.allclose(encode_penalized(p0).Q, encode_penalized(pb).Q)


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


def test_resolve_frustration_beta_ramps_with_basket_size(monkeypatch):
    # β is N-aware: 0 for tiny baskets (β hurts OOS there), ramping to the full peak fraction at
    # large baskets (qpu-experiment-synthesis §7/§9). Verifies the resolve_frustration_beta ramp.
    from backend.financial.qubo_encoder import resolve_frustration_beta, select_objective_scale
    from backend.financial.types import PortfolioProblem

    monkeypatch.setattr(config, "CARDINALITY_ENCODING", "select")
    monkeypatch.setattr(config, "CARDINALITY_FRUSTRATION_BETA", 0.4)
    monkeypatch.setattr(config, "CARDINALITY_BETA_N_MIN", 12)
    monkeypatch.setattr(config, "CARDINALITY_BETA_N_FULL", 40)

    def prob(n):
        rng = np.random.default_rng(n)
        A = rng.normal(size=(n, n))
        return PortfolioProblem(
            mu=rng.uniform(-0.01, 0.03, n),
            Sigma=A @ A.T / n + np.eye(n) * 0.02,
            gamma=2.0,
            w_max=0.5,
            w_min=1 / 32,
            asset_tickers=[str(i) for i in range(n)],
            cardinality_k=max(3, n // 3),
            n_units_M=32,
            u_min_units=1,
        )

    assert resolve_frustration_beta(prob(10)) == 0.0  # below N_MIN → off
    p40 = prob(40)
    assert resolve_frustration_beta(p40) == pytest.approx(0.4 * select_objective_scale(p40))  # full
    p28 = prob(28)  # mid → linearly ramped
    ramp = (28 - 12) / (40 - 12)
    assert resolve_frustration_beta(p28) == pytest.approx(0.4 * ramp * select_objective_scale(p28))
