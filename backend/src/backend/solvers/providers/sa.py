"""Simulated Annealing provider — solves the QUBO via dwave-neal."""

from __future__ import annotations

import time

import numpy as np

from ...financial.qubo_decoder import decode_bitstring
from ...financial.types import PortfolioProblem
from ..types import QuboMatrix, Solution, SolverFailed


def _mv_objective(weights: np.ndarray, problem: PortfolioProblem) -> float:
    risk = 0.5 * problem.gamma * weights @ problem.Sigma @ weights
    ret = problem.mu @ weights
    turnover = 0.0
    if problem.lambda_t > 0.0:
        diff = weights - problem.w_ref
        turnover = problem.lambda_t * (diff @ diff)
    return float(risk - ret + turnover)


class SAProvider:
    name = "sa"
    role = "CPU"

    def __init__(self, num_reads: int = 1000, num_sweeps: int = 1000) -> None:
        self.num_reads = num_reads
        self.num_sweeps = num_sweeps

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution:
        try:
            import neal
        except ImportError as e:
            raise SolverFailed("dwave-neal not installed") from e

        # neal wants dict form with upper-triangle keys; our symmetric Q stores
        # half the bilinear coefficient on each side, so combine Q[i,j] + Q[j,i].
        n = qubo.n
        Q = qubo.Q
        qdict: dict[tuple[int, int], float] = {}
        for i in range(n):
            qdict[(i, i)] = float(Q[i, i])
            for j in range(i + 1, n):
                v = float(Q[i, j] + Q[j, i])
                if v != 0.0:
                    qdict[(i, j)] = v

        sampler = neal.SimulatedAnnealingSampler()
        t0 = time.perf_counter()
        response = sampler.sample_qubo(qdict, num_reads=self.num_reads, num_sweeps=self.num_sweeps)
        elapsed = time.perf_counter() - t0

        best = response.first
        bits = np.array([best.sample[i] for i in range(n)], dtype=np.int8)
        weights = decode_bitstring(bits, qubo.decode_meta, normalize=True)

        return Solution(
            weights=weights,
            objective=_mv_objective(weights, problem),
            solve_time_s=elapsed,
            provider="sa",
            provider_role="CPU",
            feasible=False,  # set by the router's feasibility gate
            raw_bitstring=bits,
        )

    def solve_qp(self, problem: PortfolioProblem, deadline_s: float) -> Solution:
        raise NotImplementedError("SA solves QUBO; use solve_qubo with the encoded matrix")
