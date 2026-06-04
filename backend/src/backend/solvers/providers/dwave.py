"""D-Wave Advantage QPU provider — implemented last (pending).

Solves the **same bit-discretized QUBO** the SA provider does, just on the QPU
via the Ocean SDK — an apples-to-apples comparison on the identical encoding.
Only the body is unimplemented; the contract is in place (the `solve_qubo`
signature and the `QPU` role), so it slots straight into the router's race once
built. Until then every call raises SolverFailed, which the router treats like
any solver that produced nothing — it falls through to the classical solvers
with no special-casing.
"""

from __future__ import annotations

from ...financial.types import MIQPProblem
from ..types import QuboMatrix, Solution, SolverFailed


class DWaveProvider:
    name = "dwave"
    role = "QPU"

    def solve_qubo(self, qubo: QuboMatrix, miqp: MIQPProblem, deadline_s: float) -> Solution:
        raise SolverFailed("D-Wave provider not yet implemented (pending)")

    def solve_miqp(self, miqp: MIQPProblem, deadline_s: float) -> Solution:
        raise NotImplementedError("D-Wave solves QUBO, not MIQP")
