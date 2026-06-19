"""D-Wave Advantage QPU provider — solves the QUBO via the Ocean SDK.

Joins the race only when DWAVE_API_TOKEN is set (explicit opt-in — QPU time
costs real money; see router.build_providers). Uses DWaveCliqueSampler: our
QUBO is dense (the budget penalty couples every pair of bits), and the clique
sampler reuses precomputed clique embeddings instead of re-running a minutes-
long minor-embedding search per solve. The reported solve time is the pure
quantum anneal time (anneal-per-sample × num_reads), excluding programming/
readout/network latency; feasible races are ranked by that reported time.
"""

from __future__ import annotations

import os
import time
from functools import partial
from threading import Lock

from ... import config
from ...financial.types import PortfolioProblem
from ..sampling import select_solution
from ..types import QuboMatrix, Solution, SolverFailed

_sampler = None
_sampler_lock = Lock()


def is_configured() -> bool:
    return bool(os.environ.get("DWAVE_API_TOKEN"))


def reads_for_vars(n_vars: int) -> int:
    """num_reads for a QUBO of n_vars logical variables — see DWAVE_READS_BY_VARS."""
    for max_vars, reads in config.DWAVE_READS_BY_VARS:
        if n_vars <= max_vars:
            return reads
    return config.DWAVE_NUM_READS


def sample_kwargs(num_reads: int) -> dict:
    """Shared QPU sampling parameters (also used by the verify-dwave CLI).

    The budget penalty couples every pair of bits, so per-qubit coupling sums
    are large and the sampler's default chain strength under-protects chains —
    uniform torque compensation with a prefactor keeps them intact.
    """
    kwargs: dict = {"num_reads": num_reads, "annealing_time": config.DWAVE_ANNEAL_TIME_US}
    try:
        from dwave.embedding.chain_strength import uniform_torque_compensation

        kwargs["chain_strength"] = partial(
            uniform_torque_compensation, prefactor=config.DWAVE_CHAIN_STRENGTH_PREFACTOR
        )
    except ImportError:
        pass  # fake samplers in tests don't need it
    return kwargs


def _get_sampler():
    """Build the clique sampler once (the Leap handshake is slow)."""
    global _sampler
    with _sampler_lock:
        if _sampler is None:
            try:
                from dwave.system import DWaveCliqueSampler
            except ImportError as e:
                raise SolverFailed("dwave-system not installed") from e
            try:
                _sampler = DWaveCliqueSampler()
            except Exception as e:
                raise SolverFailed(f"D-Wave unavailable: {e}") from e
        return _sampler


class DWaveProvider:
    name = "dwave"
    role = "QPU"

    def __init__(self, sampler=None, num_reads: int | None = None) -> None:
        self._sampler = sampler  # injectable for tests
        self._num_reads = num_reads  # None → size-based schedule (reads_for_vars)

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution:
        sampler = self._sampler or _get_sampler()
        num_reads = self._num_reads if self._num_reads is not None else reads_for_vars(qubo.n)
        t0 = time.perf_counter()
        try:
            response = sampler.sample_qubo(
                qubo.to_dict(), label="qtw-tradinggame", **sample_kwargs(num_reads)
            )
        except Exception as e:
            raise SolverFailed(f"D-Wave sampling failed: {e}") from e
        wall = time.perf_counter() - t0

        weights, bits = select_solution(response, qubo, problem)
        # Report the pure quantum compute time — total annealing across all reads
        # (anneal-per-sample × num_reads) — NOT qpu_access_time, which bundles in
        # programming + readout latency. This is the QPU's actual solve cost and
        # the basis the race ranks on. Falls back to access time, then wall clock.
        timing = response.info.get("timing", {})
        anneal_per_sample_us = timing.get("qpu_anneal_time_per_sample")
        if anneal_per_sample_us:
            solve_time_s = anneal_per_sample_us * self._num_reads / 1e6
        elif timing.get("qpu_access_time"):
            solve_time_s = timing["qpu_access_time"] / 1e6
        else:
            solve_time_s = wall
        return Solution(
            weights=weights,
            objective=problem.objective(weights),
            solve_time_s=solve_time_s,
            provider="dwave",
            provider_role="QPU",
            feasible=False,  # set by the router's feasibility gate
            raw_bitstring=bits,
        )

    def solve_qp(self, problem: PortfolioProblem, deadline_s: float) -> Solution:
        raise NotImplementedError("D-Wave solves QUBO, not the continuous QP")
