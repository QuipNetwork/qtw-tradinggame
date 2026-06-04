"""Encode the mean-variance MIQP as a symmetric QUBO via bit discretization.

DERIVATION
----------

MIQP form (continuous w, binary y_i indicators):

    min   (γ/2) wᵀΣw  -  μᵀw  +  λ_t ‖w - w_ref‖²
    s.t.  Σ w_i = 1                                    (budget)
          w_min · y_i ≤ w_i ≤ w_max · y_i              (coupling + min position)
          Σ y_i = K                                    (cardinality)
          y_i ∈ {0,1}, w_i ∈ ℝ

Discretize the *span above the minimum* with b bits, so a selected asset carries
w_min plus a bit-encoded increment, and an unselected asset carries zero:

    w_i ≈ w_min · y_i + c · Σ_k 2^k · x_{i,k},   c = (w_max - w_min) / (2^b - 1)

Stack everything into the full binary vector z = [x ; y] (length N(b+1)) and a
single matrix D ∈ ℝ^(N × N(b+1)) such that **w = D z**:

    D[i, i·b + k] = c · 2^k        (weight bits)
    D[i, Nb + i]  = w_min          (minimum position when y_i = 1)

Variable layout in the QUBO bitstring:
    positions 0 .. Nb-1:        weight bits x_{i,k}  (i = pos // b, k = pos % b)
    positions Nb .. Nb+N-1:     cardinality indicators y_i

QUBO objective contributions
----------------------------

With w = D z the smooth objective is quadratic in z directly:

1. Risk + turnover:  (γ/2) wᵀΣw + λ_t wᵀw  =  zᵀ [ (γ/2) DᵀΣD + λ_t DᵀD ] z
2. Return + turnover-linear:  -μᵀw - 2λ_t w_refᵀw  =  Dᵀ(-μ - 2λ_t w_ref) · z
3. Budget penalty:  λ_sum (Σ w_i - 1)² = λ_sum (uᵀz - 1)²,  u = Dᵀ1
   → λ_sum u uᵀ on the quadratic, -2 λ_sum u on the linear (constant dropped).

Constraint penalties added on top:

4. Cardinality:  λ_K (Σ y_i - K)²
   = λ_K [ (1 - 2K) Σ y_i + 2 Σ_{i<j} y_i y_j + K² ]  → y-block only.
5. Coupling:  M Σ_{i,k} x_{i,k} (1 - y_i)  → +M on each x diagonal, -M/2 on each
   Q[x_{i,k}, y_i] (and symmetric). Forces y_i = 1 whenever a weight bit is set,
   so weight cannot be "smuggled in" without consuming a y (and thus a card slot).

CONVENTION
----------

Q is SYMMETRIC. For binary z, z_i² = z_i, so the diagonal stores all linear
coefficients. For off-diagonal pairs (i, j), the coefficient of z_i z_j in the
expanded objective is 2 · Q[i, j].
"""

from __future__ import annotations

import hashlib

import numpy as np

from .. import config
from ..solvers.types import DecodeMeta, QuboMatrix
from .types import MIQPProblem


def encode_qubo(
    miqp: MIQPProblem,
    bits_per_asset: int | None = None,
    penalty_mult_budget: float | None = None,
    penalty_mult_cardinality: float | None = None,
    coupling_mult: float | None = None,
) -> QuboMatrix:
    """Convert MIQP → QUBO. See module docstring for derivation."""

    b = bits_per_asset if bits_per_asset is not None else config.BIT_PRECISION
    pmult_budget = (
        penalty_mult_budget if penalty_mult_budget is not None else config.PENALTY_MULT_BUDGET
    )
    pmult_card = (
        penalty_mult_cardinality
        if penalty_mult_cardinality is not None
        else config.PENALTY_MULT_CARDINALITY
    )
    cmult = coupling_mult if coupling_mult is not None else config.COUPLING_MULT

    N = miqp.N
    w_min = miqp.w_min
    c = (miqp.w_max - w_min) / (2**b - 1)
    n_weight = N * b
    n_total = N * (b + 1)
    y_offset = n_weight

    # Build D over the full vector z = [x ; y] such that w = D z.
    D = np.zeros((N, n_total))
    for i in range(N):
        for k in range(b):
            D[i, i * b + k] = c * (2**k)
        D[i, y_offset + i] = w_min  # minimum position when y_i = 1

    # -------------------------------------------------------------------------
    # Objective: quadratic (γ/2) DᵀΣD + λ_t DᵀD, linear Dᵀ(-μ - 2λ_t w_ref).
    # -------------------------------------------------------------------------
    A_obj = (miqp.gamma / 2.0) * D.T @ miqp.Sigma @ D + miqp.lambda_t * D.T @ D
    b_obj = D.T @ (-miqp.mu - 2.0 * miqp.lambda_t * miqp.w_ref)

    # Penalty weights scale with the largest objective coefficient.
    obj_scale = max(float(np.abs(A_obj).max()), float(np.abs(b_obj).max()), 1.0)
    lambda_sum = pmult_budget * obj_scale
    lambda_K = pmult_card * obj_scale
    M_couple = cmult * obj_scale

    # -------------------------------------------------------------------------
    # Budget penalty: λ_sum (uᵀz - 1)² where u = Dᵀ1
    # -------------------------------------------------------------------------
    u = D.T @ np.ones(N)
    A_budget = lambda_sum * np.outer(u, u)
    b_budget = -2.0 * lambda_sum * u

    # Assemble Q: objective + budget quadratic, then linear onto the diagonal.
    Q = A_obj + A_budget
    diag = b_obj + b_budget
    for p in range(n_total):
        Q[p, p] += diag[p]

    # -------------------------------------------------------------------------
    # Coupling penalty: M Σ_{i,k} x_{i,k} (1 - y_i)
    # -------------------------------------------------------------------------
    for i in range(N):
        for k in range(b):
            p = i * b + k
            q_pos = y_offset + i
            Q[p, p] += M_couple
            Q[p, q_pos] += -M_couple / 2.0
            Q[q_pos, p] += -M_couple / 2.0

    # -------------------------------------------------------------------------
    # Cardinality penalty: λ_K (Σ y_i - K)²  (y-block)
    # -------------------------------------------------------------------------
    for i in range(N):
        Q[y_offset + i, y_offset + i] += lambda_K * (1.0 - 2.0 * miqp.K)
        for j in range(i + 1, N):
            Q[y_offset + i, y_offset + j] += lambda_K
            Q[y_offset + j, y_offset + i] += lambda_K

    assert np.allclose(Q, Q.T), "QUBO matrix must be symmetric"

    decode_meta = DecodeMeta(
        n_assets=N,
        bits_per_asset=b,
        w_max=miqp.w_max,
        w_min=w_min,
        asset_tickers=list(miqp.asset_tickers),
    )
    return QuboMatrix(Q=Q, decode_meta=decode_meta)


def qubo_hash(qubo: QuboMatrix) -> str:
    """Stable SHA-256 of the QUBO matrix for audit logs."""
    return hashlib.sha256(qubo.Q.tobytes()).hexdigest()
