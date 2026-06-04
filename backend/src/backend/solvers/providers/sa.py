"""Simulated Annealing solver via dwave-neal.

Solves the QUBO form. Uses the same `neal` package D-Wave's Ocean SDK ships
for SA, which keeps the apples-to-apples comparison fair against D-Wave.
"""

from __future__ import annotations

import time

import numpy as np

from ...financial.qubo_decoder import decode_bitstring
from ...financial.types import MIQPProblem
from ..types import QuboMatrix, Solution, SolverFailed


def _mv_objective(weights: np.ndarray, miqp: MIQPProblem) -> float:
    """Evaluate the true mean-variance objective at the decoded weights."""
    risk = 0.5 * miqp.gamma * weights @ miqp.Sigma @ weights
    ret = miqp.mu @ weights
    if miqp.lambda_t > 0.0:
        diff = weights - miqp.w_ref
        turnover = miqp.lambda_t * (diff @ diff)
    else:
        turnover = 0.0
    return float(risk - ret + turnover)


class SAProvider:
    name = "sa"
    role = "CPU"

    def __init__(self, num_reads: int = 1000, num_sweeps: int = 1000) -> None:
        self.num_reads = num_reads
        self.num_sweeps = num_sweeps

    def solve_qubo(self, qubo: QuboMatrix, miqp: MIQPProblem, deadline_s: float) -> Solution:
        try:
            import neal
        except ImportError as e:
            raise SolverFailed("dwave-neal not installed") from e

        # neal expects a dict-form QUBO with (i, j) keys for i <= j.
        # Our Q is symmetric; the off-diagonal coefficient on x_i x_j in the
        # bilinear form is 2 · Q[i,j], so we sum upper + lower into a single
        # upper-triangle entry.
        n = qubo.n
        Q = qubo.Q
        qdict: dict[tuple[int, int], float] = {}
        for i in range(n):
            qdict[(i, i)] = float(Q[i, i])
            for j in range(i + 1, n):
                # Combined coefficient on x_i x_j is Q[i,j] + Q[j,i] = 2 Q[i,j].
                v = float(Q[i, j] + Q[j, i])
                if v != 0.0:
                    qdict[(i, j)] = v

        sampler = neal.SimulatedAnnealingSampler()
        t0 = time.perf_counter()
        response = sampler.sample_qubo(qdict, num_reads=self.num_reads, num_sweeps=self.num_sweeps)
        elapsed = time.perf_counter() - t0

        # Take the lowest-energy sample.
        best = response.first
        bits = np.array([best.sample[i] for i in range(n)], dtype=np.int8)

        weights = decode_bitstring(bits, qubo.decode_meta)
        objective = _mv_objective(weights, miqp)

        return Solution(
            weights=weights,
            objective=objective,
            solve_time_s=elapsed,
            provider="sa",
            provider_role="CPU",
            feasible=False,  # set by router after running feasibility check
            raw_bitstring=bits,
        )

    def solve_miqp(self, miqp: MIQPProblem, deadline_s: float) -> Solution:
        # SA needs QUBO form — router handles encoding.
        raise NotImplementedError("SA solves QUBO; use solve_qubo with encoded matrix")
