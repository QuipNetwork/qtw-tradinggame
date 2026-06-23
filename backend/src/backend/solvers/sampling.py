"""Pick the best decodable solution from a sampler response.

A QUBO sampler's lowest-energy sample can still violate the budget (penalties
compete with the objective, and QPU noise/chain breaks blur small coefficients).
Scanning every read for the best *feasible* decode costs microseconds and
recovers solutions the energy ordering would discard.
"""

from __future__ import annotations

import numpy as np

from .. import config
from ..financial.projection import greedy_project, weights_for_support
from ..financial.qubo_decoder import decode_bitstring
from ..financial.types import PortfolioProblem, correlation_matrix
from .feasibility import check_feasibility
from .types import QuboMatrix


def reads_for_vars(n_vars: int) -> int:
    """num_reads for a QUBO of n_vars logical variables — see config.DWAVE_READS_BY_VARS. Shared by
    the SA and D-Wave providers so both draw the same size-scaled read budget (apples-to-apples);
    lives here (not in the D-Wave provider) so the CPU solver doesn't depend on the QPU module."""
    for max_vars, reads in config.DWAVE_READS_BY_VARS:
        if n_vars <= max_vars:
            return reads
    return config.DWAVE_NUM_READS


def select_solution(
    response, qubo: QuboMatrix, problem: PortfolioProblem
) -> tuple[np.ndarray, np.ndarray]:
    """Return (weights, bits) of the best feasible sample by true objective,
    falling back to the lowest-energy sample when none is feasible."""
    if qubo.decode_meta.scheme == "select":
        return _select_solution_c2(response, qubo, problem)

    best_objective = None
    best: tuple[np.ndarray, np.ndarray] | None = None
    fallback: tuple[np.ndarray, np.ndarray] | None = None

    for sample in _samples(response):
        bits = np.array([sample[i] for i in range(qubo.n)], dtype=np.int8)
        weights = decode_bitstring(bits, qubo.decode_meta, normalize=True)
        if fallback is None:
            fallback = (weights, bits)
        feas = check_feasibility(
            weights, problem.w_max, problem.w_min, cardinality_k=problem.cardinality_k
        )
        if feas.feasible:
            objective = problem.objective(weights)
            if best_objective is None or objective < best_objective:
                best_objective = objective
                best = (weights, bits)

    return best if best is not None else fallback


def _select_solution_c2(
    response, qubo: QuboMatrix, problem: PortfolioProblem
) -> tuple[np.ndarray, np.ndarray]:
    """C2 (penalty-free selection): project EVERY read to exactly-K (greedy), set the weights by
    the convex QP, score by the true objective; return the best portfolio. Cardinality/budget/box
    are enforced HERE (not in the QUBO), so every read yields a feasible portfolio — the identical
    classical finish for SA and D-Wave (apples-to-apples; removes the QPU feasibility handicap)."""
    n = problem.N
    # Hoist the correlation matrix out of the per-read loop (greedy_project would otherwise
    # rebuild it every read); cache (weights, objective) per UNIQUE support so the QP and
    # objective() run once per distinct selection, not once per read.
    rho = correlation_matrix(problem.Sigma) if problem.frustration_beta else None
    best_obj: float | None = None
    best: tuple[np.ndarray, np.ndarray] | None = None
    cache: dict[tuple[int, ...], tuple[np.ndarray, float]] = {}  # support → (weights, objective)

    for sample in _samples(response):
        bits = np.array([sample[i] for i in range(qubo.n)], dtype=np.int8)
        support = greedy_project(bits, problem, rho)
        hit = cache.get(support)
        if hit is None:
            weights = weights_for_support(support, problem)
            hit = (weights, problem.objective(weights))
            cache[support] = hit
        weights, objective = hit
        if best_obj is None or objective < best_obj:
            best_obj = objective
            best = (weights, bits)

    if best is None:  # no samples (defensive); degenerate empty portfolio → router gates it out
        return np.zeros(n), np.zeros(qubo.n, dtype=np.int8)
    return best


def _samples(response):
    """Samples in energy-ascending order; tolerates minimal fake samplers."""
    try:
        return response.samples()
    except AttributeError:
        return [response.first.sample]
