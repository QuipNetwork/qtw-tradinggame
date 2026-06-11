"""D-Wave Advantage QPU provider — implemented last (pending).

Solves the same bit-discretized QUBO the SA provider does, on the QPU via the
Ocean SDK. The contract is in place so it slots straight into the race; until
then every call raises SolverFailed and the router falls through to the
classical solvers.
"""

from __future__ import annotations

from ...financial.types import PortfolioProblem
from ..types import QuboMatrix, Solution, SolverFailed


class DWaveProvider:
    name = "dwave"
    role = "QPU"

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution:
        raise SolverFailed("D-Wave provider not yet implemented (pending)")

    def solve_qp(self, problem: PortfolioProblem, deadline_s: float) -> Solution:
        raise NotImplementedError("D-Wave solves QUBO, not the continuous QP")
