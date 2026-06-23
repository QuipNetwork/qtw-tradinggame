"""Encode the mean-variance QP as a symmetric QUBO via bit discretization.

DERIVATION
----------

QP form (continuous w over the player's n-asset basket):

    min   (γ/2) wᵀΣw  -  μᵀw
    s.t.  Σ w_i = 1                  (budget)
          w_min ≤ w_i ≤ w_max        (box)

There is no cardinality constraint — basket selection already decides which
assets participate — so the encoding needs no indicator variables and no
coupling penalties. Each weight is w_min plus a b-bit increment:

    w_i = w_min + c · Σ_k 2^k · x_{i,k},   x_{i,k} ∈ {0,1},
    c = (w_max - w_min) / (2^b - 1)

In matrix form w = w_min·1 + D x with D ∈ ℝ^(n × nb), D[i, i·b + k] = c·2^k.
The box constraint is implicit in the encoding (all-zero bits → w_min,
all-one bits → w_max).

QUBO objective contributions (z := x, length nb)
------------------------------------------------

Substituting w = m + Dx (m := w_min·1) into the smooth objective:

1. Quadratic:  xᵀ [ (γ/2) DᵀΣD ] x
2. Linear:     Dᵀ [ γ Σ m - μ ] · x
   (constants in m alone are dropped — they don't affect the argmin)

Budget penalty λ_sum (Σw - 1)² with Σw = n·w_min + uᵀx, u = Dᵀ1:
    = λ_sum (uᵀx - r)²,  r := 1 - n·w_min
    → λ_sum u uᵀ on the quadratic, -2 λ_sum r u on the linear.

    λ_sum := pmult · obj_scale / u_max²  (u_max = max u = c·2^(b-1)), so that
    max|A_budget| = pmult · max|A_obj| — pmult is the penalty:objective peak-
    coefficient ratio, invariant to n, b, and w_max.

CONVENTION
----------

Q is SYMMETRIC. For binary x, x_i² = x_i, so the diagonal stores all linear
coefficients. For off-diagonal pairs (i, j), the coefficient of x_i x_j in the
expanded objective is 2 · Q[i, j].
"""

from __future__ import annotations

import hashlib

import numpy as np

from .. import config
from ..solvers.types import DecodeMeta, QuboMatrix
from .types import PortfolioProblem, correlation_matrix


def bits_for_basket(n_assets: int) -> int:
    """Full precision while the QUBO stays small; 3 bits for large baskets
    (see config — QPU coupler dynamic range, not solver capacity, is the limit)."""
    if n_assets * config.BIT_PRECISION <= config.QUBO_PREFERRED_MAX_VARS:
        return config.BIT_PRECISION
    return config.BIT_PRECISION_LARGE


def units_for_cardinality(k: int) -> int:
    """cardinality grid size M for cardinality k: the smallest power of two ≥ k (must
    have M ≥ k units to place k held assets), floored/capped by config. Smaller M =
    fewer increment bits = fewer QUBO variables, which is the QPU-feasibility lever
    (see config CARDINALITY_MIN/MAX_UNITS and the encode_penalized b = log2(M)−1 layout)."""
    floor = max(k, config.CARDINALITY_MIN_UNITS)
    m = 1 << (floor - 1).bit_length()  # next power of two ≥ floor
    return min(m, config.CARDINALITY_MAX_UNITS)


def units_for_grid(k: int, basket_size: int) -> int:
    """cardinality grid size M, SIZE-AWARE (mirrors convex bits_for_basket). Raises M toward a
    FINER grid (more weight levels ≈ closer to continuous) for small baskets that stay
    embeddable, keeps it COARSE for large baskets so the dense QUBO still embeds. Always
    floored so M ≥ K. vars = N·log2(M), so CARDINALITY_PREFERRED_MAX_VARS caps resolution by N.
    Bigger small-basket QUBOs also slow SA (cost ~vars²), keeping the QPU race-competitive."""
    m = units_for_cardinality(k)  # K floor (and ≥ CARDINALITY_MIN_UNITS)
    cand = config.CARDINALITY_MIN_UNITS
    while cand * 2 <= config.CARDINALITY_MAX_UNITS:
        cand *= 2  # next finer power-of-two grid
        if basket_size * (cand.bit_length() - 1) <= config.CARDINALITY_PREFERRED_MAX_VARS:
            m = max(m, cand)  # afford the finer grid only if vars stay within budget
    return min(m, config.CARDINALITY_MAX_UNITS)


def increment_place_values(w_max: float, n_units_M: int, u_min: int, b: int) -> np.ndarray:
    """Place values for one held asset's b increment bits (cardinality).

    Caps a held asset at u_cap = ⌊w_max·M⌋ units so the integer grid never exceeds the
    per-asset box (w_i ≤ w_max) — a bounded-coefficient encoding [1, 2, …, remainder].
    With the default w_max = 0.5 the remainder vanishes and this is plain 2^k. Encoder
    and decoder both call this, so the layout (and the cap) cannot drift between them."""
    c_max = max(0, int(np.floor(w_max * n_units_M)) - u_min)  # max increment above u_min
    coeffs = np.zeros(b)
    acc = 0
    for k in range(b):
        step = 1 << k
        if acc + step <= c_max:
            coeffs[k] = step
            acc += step
        else:
            coeffs[k] = c_max - acc  # remainder bit; subsequent coeffs stay 0
            break
    return coeffs


def _add_frustration_coupling(Q: np.ndarray, rho: np.ndarray, beta: float, n: int) -> None:
    """Add the diversification reward β·Σ_{i<j} ρ_ij x_i x_j to symmetric matrix Q, in place.

    Splits 0.5·β·ρ_ij across the (i,j) and (j,i) halves so QuboMatrix.to_dict() recombines them
    into β·ρ_ij per pair. Couples the first n variables (asset i's select bit is index i in both
    the select and cardinality layouts), diagonal untouched. Shared by encode_select and encode_penalized
    so the β convention can never drift between them.
    """
    coupling = 0.5 * beta * rho[:n, :n].copy()
    np.fill_diagonal(coupling, 0.0)
    Q[:n, :n] += coupling


def encode_qubo(
    problem: PortfolioProblem,
    bits_per_asset: int | None = None,
    penalty_mult_budget: float | None = None,
) -> QuboMatrix:
    """Convert the box-constrained QP → QUBO. See module docstring.

    Dispatches to ``encode_penalized`` for cardinality/semi-continuous problems.
    """
    if problem.is_cardinality:
        if config.CARDINALITY_ENCODING == "select":
            return encode_select(problem)
        return encode_penalized(problem)

    b = bits_per_asset if bits_per_asset is not None else bits_for_basket(problem.N)
    pmult_budget = (
        penalty_mult_budget if penalty_mult_budget is not None else config.PENALTY_MULT_BUDGET
    )

    N = problem.N
    w_min = problem.w_min
    c = (problem.w_max - w_min) / (2**b - 1)
    n_bits = N * b

    # Build D such that w = w_min·1 + D x  (shape (N, n_bits))
    D = np.zeros((N, n_bits))
    for i in range(N):
        for k in range(b):
            D[i, i * b + k] = c * (2**k)

    m = np.full(N, w_min)  # the constant offset vector

    A_obj = (problem.gamma / 2.0) * D.T @ problem.Sigma @ D
    b_obj = D.T @ (problem.gamma * (problem.Sigma @ m) - problem.mu)

    # -------------------------------------------------------------------------
    # Budget penalty: λ_sum (uᵀx - r)²,  u = Dᵀ1,  r = 1 - N·w_min
    # -------------------------------------------------------------------------
    u = D.T @ np.ones(N)
    r = 1.0 - N * w_min

    # Normalize λ_sum by the budget term's own quadratic scale (u_max²) so pmult
    # IS the penalty:objective peak-coefficient ratio, independent of basket size,
    # bit depth, and w_max — i.e. max|A_budget| = pmult · max|A_obj|. Without the
    # /u_max², the *effective* ratio is pmult·u_max², which swings ~270× across the
    # max-position slider (25-asset basket) and under-penalizes the budget at low
    # w_max → Σw drift. The epsilon clamps keep the ratio finite and bounded; a
    # runaway ratio (~10⁶) would erase the objective below QPU coupler precision.
    obj_scale = max(float(np.abs(A_obj).max()), float(np.abs(b_obj).max()), 1e-12)
    u_max_sq = max(float((u**2).max()), 1e-12)
    lambda_sum = pmult_budget * obj_scale / u_max_sq

    A_budget = lambda_sum * np.outer(u, u)
    b_budget = -2.0 * lambda_sum * r * u

    # Assemble Q: quadratic blocks, then linear onto the diagonal.
    Q = A_obj + A_budget
    diag = b_obj + b_budget
    for p in range(n_bits):
        Q[p, p] += diag[p]

    assert np.allclose(Q, Q.T), "QUBO matrix must be symmetric"

    decode_meta = DecodeMeta(
        n_assets=N,
        bits_per_asset=b,
        w_max=problem.w_max,
        w_min=w_min,
        asset_tickers=list(problem.asset_tickers),
    )
    return QuboMatrix(Q=Q, decode_meta=decode_meta)


def encode_select(problem: PortfolioProblem) -> QuboMatrix:
    """Penalty-free SELECTION-ONLY QUBO (C2): one binary x_i per asset, no weight bits.

    Minimizes the equal-weight (1/K) surrogate of subset value
        −(1/K)·Σ μ_i x_i  +  (γ/2K²)·Σ_ij Σ_ij x_i x_j
    plus the diversification reward β·Σ_{i<j} ρ_ij x_i x_j. NO budget/cardinality penalties:
    the greedy projector enforces exactly-K and a convex QP (financial.weighting.optimal_weights)
    sets the weights, both classically (see solvers.sampling). The QUBO is sparse (no constraint
    clique), so D-Wave embeds with short chains and every read is feasible after projection. On
    the rugged β>0 landscape D-Wave beats SA on portfolio quality. See qpu-c2-beta-findings.md.
    """
    assert problem.is_cardinality, "encode_select requires cardinality_k"
    N = problem.N
    k = problem.cardinality_k
    coef = problem.gamma / (2.0 * k * k)  # symmetric-matrix half of the (γ/K²)Σ_ij pair term

    # Off-diagonals = (γ/2K²)Σ_ij; diagonal = −μ_i/K + (γ/2K²)Σ_ii (x_i² = x_i). Via to_dict the
    # pair coefficient becomes (γ/K²)Σ_ij — the equal-weight risk−return surrogate over subsets.
    Q = coef * problem.Sigma.astype(float)
    for i in range(N):
        Q[i, i] = -problem.mu[i] / k + coef * problem.Sigma[i, i]

    # Diversification / frustration reward β·Σ_{i<j} ρ_ij x_i x_j.
    if problem.frustration_beta:
        _add_frustration_coupling(Q, correlation_matrix(problem.Sigma), problem.frustration_beta, N)

    assert np.allclose(Q, Q.T), "QUBO matrix must be symmetric"
    decode_meta = DecodeMeta(
        n_assets=N,
        bits_per_asset=1,
        w_max=problem.w_max,
        w_min=problem.w_min,
        asset_tickers=list(problem.asset_tickers),
        scheme="select",
        n_units_M=problem.n_units_M,
        u_min_units=problem.u_min_units,
        increment_bits=0,
    )
    return QuboMatrix(Q=Q, decode_meta=decode_meta)


def select_objective_scale(problem: PortfolioProblem) -> float:
    """Peak |coefficient| of the C2 selection objective (the to_dict scale ``encode_select`` uses):
    max over −μ_i/K + (γ/2K²)Σ_ii (diagonal) and (γ/K²)Σ_ij (pairs). This is the per-problem scale
    that lets CARDINALITY_FRUSTRATION_BETA be a basket-invariant fraction (see resolve_frustration_beta).
    """
    k, g = problem.cardinality_k, problem.gamma
    coef = g / (2.0 * k * k)
    diag = np.abs(-problem.mu / k + coef * np.diagonal(problem.Sigma))
    off = 2.0 * coef * np.abs(problem.Sigma)
    np.fill_diagonal(off, 0.0)
    return float(max(diag.max(), off.max(), 1e-12))


def resolve_frustration_beta(problem: PortfolioProblem) -> float:
    """Effective absolute β for ``problem`` (select encoding only; 0 for convex/penalized).

    CARDINALITY_FRUSTRATION_BETA is the PEAK fraction of the objective scale; it is (a) multiplied by
    select_objective_scale so the relative diversification pressure is basket-invariant, and (b)
    RAMPED by basket size N — 0 below CARDINALITY_BETA_N_MIN, full at/above CARDINALITY_BETA_N_FULL, linear
    between — because OOS backtests show β helps at scale but hurts tiny baskets
    (qpu-experiment-synthesis-2026-06-22.md §7/§9)."""
    beta_max = config.CARDINALITY_FRUSTRATION_BETA
    if not (beta_max and problem.is_cardinality and config.CARDINALITY_ENCODING == "select"):
        return 0.0
    lo, hi = config.CARDINALITY_BETA_N_MIN, config.CARDINALITY_BETA_N_FULL
    ramp = min(1.0, max(0.0, (problem.N - lo) / max(1, hi - lo)))
    return beta_max * ramp * select_objective_scale(problem)


def encode_penalized(
    problem: PortfolioProblem,
    *,
    increment_bits: int | None = None,
    pmult_budget: float | None = None,
    pmult_card: float | None = None,
    pmult_link: float | None = None,
) -> QuboMatrix:
    """Cardinality + semi-continuous MIQP → integer-units selection QUBO.

    Variables z = [y_0..y_{N-1}, x_{0,0}..x_{N-1,b-1}]:
        y_i ∈ {0,1}      select asset i
        x_{i,k} ∈ {0,1}  increment bits
        units  u_i = u_min·y_i + Σ_k 2^k x_{i,k};   weight w_i = u_i / M

    Objective (γ/2M²)uᵀΣu − (1/M)μᵀu plus three penalties — budget λ_bud(Σu−M)²,
    cardinality λ_card(Σy−k)², linking λ_link Σ x_{i,k}(1−y_i) (no increment without
    selection). Integer units make Σu=M exactly representable. Each penalty's peak
    coefficient is normalized to pmult·obj_scale, so the pmults are config-invariant
    ratios (same philosophy as the convex budget penalty). Reference + validation:
    sketches/method3_integer_units_qubo.py.
    """
    assert problem.is_cardinality, "encode_penalized requires cardinality_k / n_units_M"
    N = problem.N
    M = problem.n_units_M
    u_min = problem.u_min_units
    k = problem.cardinality_k
    # b = log2(M) − 1 (u_min=1, grid [1/M, 0.5]); the grid size M (from
    # units_for_cardinality) is the single source of the bit depth.
    b = increment_bits if increment_bits is not None else (M.bit_length() - 2)
    pmult_budget = pmult_budget if pmult_budget is not None else config.PENALTY_MULT_BUDGET
    pmult_card = pmult_card if pmult_card is not None else config.CARDINALITY_PENALTY_MULT_CARD
    pmult_link = pmult_link if pmult_link is not None else config.CARDINALITY_PENALTY_MULT_LINK

    nv = N * (1 + b)

    def yidx(i: int) -> int:
        return i

    def xidx(i: int, kk: int) -> int:
        return N + i * b + kk

    # u = G z  (floor on the select bit, w_max-bounded place values on the increment
    # bits, so a held asset can never exceed ⌊w_max·M⌋ units — see increment_place_values).
    inc_coeffs = increment_place_values(problem.w_max, M, u_min, b)
    G = np.zeros((N, nv))
    for i in range(N):
        G[i, yidx(i)] = u_min
        for kk in range(b):
            G[i, xidx(i, kk)] = inc_coeffs[kk]

    # Objective: (γ/2M²) uᵀΣu − (1/M) μᵀu.  (zᵀQm z + linᵀz is exactly the economic
    # objective in u-space, since w = u/M and Qm = (γ/2M²)GᵀΣG.)
    Qm = (problem.gamma / (2.0 * M * M)) * (G.T @ problem.Sigma @ G)
    lin = -(1.0 / M) * (G.T @ problem.mu)

    # Diversification / frustration reward β·Σ_{i<j} ρ_ij·y_i·y_j on the SELECT bits (indices
    # 0..N-1, yidx = identity). Added BEFORE obj_scale so the constraint penalties below still
    # dominate it and feasibility is preserved.
    if problem.frustration_beta:
        _add_frustration_coupling(
            Qm, correlation_matrix(problem.Sigma), problem.frustration_beta, N
        )

    obj_scale = max(float(np.abs(Qm).max()), float(np.abs(lin).max()), 1e-12)

    # Budget penalty λ_bud (vᵀz − M)², v = Gᵀ1 — peak normalized to pmult·obj_scale.
    v = G.T @ np.ones(N)
    v_max_sq = max(float((v**2).max()), 1e-12)
    lam_bud = pmult_budget * obj_scale / v_max_sq
    Qm += lam_bud * np.outer(v, v)
    lin += lam_bud * (-2.0 * M) * v

    # Cardinality penalty λ_card (sᵀz − k)², s = 1 on the select bits (peak |s⊗s|=1).
    s = np.zeros(nv)
    for i in range(N):
        s[yidx(i)] = 1.0
    lam_card = pmult_card * obj_scale
    Qm += lam_card * np.outer(s, s)
    lin += lam_card * (-2.0 * k) * s

    # Linking penalty λ_link Σ x(1−y) = λ_link·x − λ_link·x·y.
    lam_link = pmult_link * obj_scale
    for i in range(N):
        yv = yidx(i)
        for kk in range(b):
            xv = xidx(i, kk)
            lin[xv] += lam_link
            Qm[xv, yv] += -lam_link / 2.0
            Qm[yv, xv] += -lam_link / 2.0

    # Assemble symmetric Q; fold linear onto the diagonal (z²=z).
    Q = Qm
    for p in range(nv):
        Q[p, p] += lin[p]
    assert np.allclose(Q, Q.T), "QUBO matrix must be symmetric"

    decode_meta = DecodeMeta(
        n_assets=N,
        bits_per_asset=b,
        w_max=problem.w_max,
        w_min=problem.w_min,
        asset_tickers=list(problem.asset_tickers),
        scheme="penalized",
        n_units_M=M,
        u_min_units=u_min,
        increment_bits=b,
    )
    return QuboMatrix(Q=Q, decode_meta=decode_meta)


def qubo_hash(qubo: QuboMatrix) -> str:
    """Stable SHA-256 of the QUBO matrix for audit logs."""
    return hashlib.sha256(qubo.Q.tobytes()).hexdigest()
