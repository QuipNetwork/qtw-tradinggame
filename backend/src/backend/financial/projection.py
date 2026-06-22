"""Greedy projection of a selection-QUBO sample to exactly-K assets.

The penalty-free selection QUBO (`encode_select`) does not pin how many assets a sample turns
on, so each sampled bitstring is repaired here to exactly ``cardinality_k`` by single-asset
moves that most improve the equal-weight subset value (drop the weakest held / add the best
unheld). Pairs with `financial.weighting.optimal_weights` (the convex QP) for the weights.

Validated equal to exact best-K-of-pool enumeration at booth scale (see qpu-c2-beta-findings.md):
the sampler does the combinatorial pruning, this just finalizes the count.
"""

from __future__ import annotations

import numpy as np

from .types import PortfolioProblem, correlation_matrix
from .weighting import optimal_weights


def _subset_value(support: set[int], problem: PortfolioProblem, rho: np.ndarray | None) -> float:
    """Equal-weight (1/K) subset value — matches `encode_select` and `PortfolioProblem.objective`:
    (γ/2K²)·Σ_{i,j∈S}Σ_ij − (1/K)·Σ_{i∈S}μ_i + β·Σ_{i<j∈S}ρ_ij. Lower is better."""
    if not support:
        return 0.0
    idx = list(support)
    k = problem.cardinality_k
    val = (problem.gamma / (2.0 * k * k)) * problem.Sigma[np.ix_(idx, idx)].sum()
    val -= problem.mu[idx].sum() / k
    if problem.frustration_beta and rho is not None:
        sub = rho[np.ix_(idx, idx)]
        val += problem.frustration_beta * 0.5 * (sub.sum() - len(idx))  # Σ_{i<j} ρ_ij
    return float(val)


def greedy_project(
    selection_bits: np.ndarray, problem: PortfolioProblem, rho: np.ndarray | None = None
) -> tuple[int, ...]:
    """Repair a selection bitstring to exactly ``cardinality_k`` held assets (greedy on value).

    Pass a precomputed ``rho`` (correlation matrix) to avoid rebuilding it per read on the hot path.
    """
    n = problem.N
    # slider_map guarantees k ≤ n (and __post_init__ asserts it); clamp defends callers and
    # python -O runs so the add-loop's min() never sees an empty candidate set.
    k = min(problem.cardinality_k, n)
    if rho is None and problem.frustration_beta:
        rho = correlation_matrix(problem.Sigma)
    support = {int(i) for i in np.nonzero(selection_bits[:n])[0]}
    while len(support) > k:
        support.discard(min(support, key=lambda i: _subset_value(support - {i}, problem, rho)))
    while len(support) < k:
        support.add(
            min(
                (i for i in range(n) if i not in support),
                key=lambda i: _subset_value(support | {i}, problem, rho),
            )
        )
    return tuple(sorted(support))


def weights_for_support(
    support: tuple[int, ...] | list[int], problem: PortfolioProblem
) -> np.ndarray:
    """Convex weight QP on a fixed support, scattered into an N-vector (0 off-support).

    The one place the chosen-support → weights step lives: shared by ``select_weights`` (one sample)
    and the live race's per-support cache in ``solvers.sampling``, so the QP-and-scatter can't drift.
    """
    idx = list(support)
    w = np.zeros(problem.N)
    w[idx] = optimal_weights(
        problem.mu[idx],
        problem.Sigma[np.ix_(idx, idx)],
        problem.gamma,
        problem.w_min,
        problem.w_max,
    )
    return w


def select_weights(
    selection_bits: np.ndarray, problem: PortfolioProblem, rho: np.ndarray | None = None
) -> np.ndarray:
    """Full C2 decode of one selection sample: greedy-project to K, then the convex weight QP.

    Returns an N-vector (0 off the chosen support). Shared by the live race and ``verify-dwave``.
    """
    return weights_for_support(greedy_project(selection_bits, problem, rho), problem)
