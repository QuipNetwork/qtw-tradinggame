"""Simulated Annealing provider — solves the QUBO via dwave-neal."""

from __future__ import annotations

import time

from ...financial.types import PortfolioProblem
from ..sampling import select_solution
from ..types import QuboMatrix, Solution, SolverFailed
from .dwave import reads_for_vars


class SAProvider:
    name = "sa"
    role = "CPU"

    def __init__(self, num_reads: int = 500, num_sweeps: int = 500, sampler=None) -> None:
        self.num_reads = num_reads  # baseline floor (always ≥ this)
        self.num_sweeps = num_sweeps
        self._sampler = sampler  # injectable for tests

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution:
        # Apples-to-apples: match D-Wave's size-scaled read budget when it exceeds our 500
        # baseline, so both solvers draw the same number of samples on large QUBOs (and SA
        # isn't handicapped vs the QPU's extra reads). Small problems keep the 500 floor.
        num_reads = max(self.num_reads, reads_for_vars(qubo.n))
        if self._sampler is not None:
            sampler = self._sampler
        else:
            try:
                import neal
            except ImportError as e:
                raise SolverFailed("dwave-neal not installed") from e
            sampler = neal.SimulatedAnnealingSampler()
        t0 = time.perf_counter()
        response = sampler.sample_qubo(
            qubo.to_dict(), num_reads=num_reads, num_sweeps=self.num_sweeps
        )
        elapsed = time.perf_counter() - t0

        weights, bits = select_solution(response, qubo, problem)

        return Solution(
            weights=weights,
            objective=problem.objective(weights),
            solve_time_s=elapsed,
            provider="sa",
            provider_role="CPU",
            feasible=False,  # set by the router's feasibility gate
            raw_bitstring=bits,
        )

    def solve_qp(self, problem: PortfolioProblem, deadline_s: float) -> Solution:
        raise NotImplementedError("SA solves QUBO; use solve_qubo with the encoded matrix")
