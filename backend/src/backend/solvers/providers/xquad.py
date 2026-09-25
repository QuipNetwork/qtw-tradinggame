"""xquad 0.4.0 solver adapter for Quip testnet and local direct providers."""

from __future__ import annotations

import os
import time
from typing import Literal

import numpy as np

from ... import config
from ...financial.types import PortfolioProblem
from ..sampling import select_solution
from ..types import ProviderName, ProviderRole, QuboMatrix, Solution
from ..xquad_model import to_xqmx

XquadBackend = Literal["quip", "dwave-qpu", "dwave-cpu"]
BACKENDS = ("quip", "dwave-qpu", "dwave-cpu")
_NAMES: dict[XquadBackend, ProviderName] = {
    "quip": "xquad-quip",
    "dwave-qpu": "xquad-dwave-qpu",
    "dwave-cpu": "xquad-dwave-cpu",
}
_ROLES: dict[XquadBackend, ProviderRole] = {
    "quip": "NETWORK",
    "dwave-qpu": "QPU",
    "dwave-cpu": "CPU",
}


def selected_backend() -> XquadBackend | None:
    value = os.environ.get("XQUAD_BACKEND", "").strip().lower()
    if not value or value == "off":
        return None
    if value not in BACKENDS:
        raise ValueError(f"XQUAD_BACKEND must be one of off, {', '.join(BACKENDS)}")
    return value


def remote_requested() -> bool:
    return selected_backend() in ("quip", "dwave-qpu")


class XquadProvider:
    def __init__(self, backend: XquadBackend, *, solver=None) -> None:
        if backend not in BACKENDS:
            raise ValueError(f"unknown xquad backend: {backend}")
        self.backend = backend
        self.name = _NAMES[backend]
        self.role = _ROLES[backend]
        self._solver = solver

    def _make_solver(self, deadline_s: float):
        from xqsa import SolverDWaveCPU, SolverDWaveQPU, SolverQuip

        if self.backend == "quip":
            # The portfolio QUBO is dense (a clique over the basket), so it is
            # submitted over its own coupling graph rather than placed on a
            # hardware topology. Only embedding-free (SA/Gibbs) miners answer it.
            return SolverQuip(
                url=config.QUIP_RPC_URL,
                faucet=config.QUIP_FAUCET_URL,
                topology="native",
                timeout=max(1.0, min(deadline_s - 5.0, config.XQUAD_TIMEOUT_S)),
            )
        if self.backend == "dwave-qpu":
            return SolverDWaveQPU(num_reads=config.DWAVE_NUM_READS)
        return SolverDWaveCPU(num_reads=config.DWAVE_NUM_READS)

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution:
        model, _scale = to_xqmx(qubo)
        solver = self._solver if self._solver is not None else self._make_solver(deadline_s)
        started = time.perf_counter()
        result = solver.solve(model)
        elapsed = time.perf_counter() - started
        sample = result.sample
        if sample.size != qubo.n:
            raise ValueError(f"xquad returned {sample.size} variables, expected {qubo.n}")
        values = [sample.get_linear(i) for i in range(qubo.n)]
        if any(value not in (0, 1) for value in values):
            raise ValueError("xquad returned a non-binary sample")
        bits = np.array(values, dtype=np.int8)

        class _SingleSample:
            def samples(self):
                return [{i: int(bit) for i, bit in enumerate(bits)}]

        weights, bits = select_solution(_SingleSample(), qubo, problem)
        return Solution(
            weights=weights,
            objective=problem.objective(weights),
            solve_time_s=elapsed,
            provider=self.name,
            provider_role=self.role,
            feasible=False,
            raw_bitstring=bits,
            order_id=str(result.metadata["order_id"]) if "order_id" in result.metadata else None,
        )
