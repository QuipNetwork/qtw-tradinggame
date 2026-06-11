"""Provider protocol — what every solver implements."""

from __future__ import annotations

from typing import Protocol

from ...financial.types import PortfolioProblem
from ..types import QuboMatrix, Solution


class SolverProvider(Protocol):
    """Gurobi solves the continuous QP natively; QUBO solvers (SA, D-Wave)
    take the bit-discretized encoding, with `problem` available for evaluating
    the true objective on decoded weights."""

    name: str
    role: str  # 'QPU' | 'CPU'

    def solve_qp(self, problem: PortfolioProblem, deadline_s: float) -> Solution: ...

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution: ...
