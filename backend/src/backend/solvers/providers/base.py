"""Provider protocol — what every solver implements."""

from __future__ import annotations

from typing import Protocol

from ...financial.types import MIQPProblem
from ..types import QuboMatrix, Solution


class SolverProvider(Protocol):
    """Solver protocol.

    QUBO solvers (D-Wave, SA) implement `solve_qubo`. The MIQP solver (Gurobi)
    implements `solve_miqp` on the native form. The router calls whichever
    method is available for each provider.
    """

    name: str
    role: str  # 'QPU' | 'CPU'

    def solve_miqp(self, miqp: MIQPProblem, deadline_s: float) -> Solution:
        """Solve the MIQP form directly. Implemented by Gurobi only."""
        ...

    def solve_qubo(self, qubo: QuboMatrix, miqp: MIQPProblem, deadline_s: float) -> Solution:
        """Solve the QUBO form, using miqp for objective re-evaluation after decode.

        `miqp` is passed in so the solver can compute the true mean-variance
        objective on the decoded weights (rather than the QUBO objective, which
        includes penalties).
        """
        ...
