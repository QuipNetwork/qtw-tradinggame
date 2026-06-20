"""D-Wave Advantage QPU provider — solves the QUBO via the Ocean SDK.

Joins the race only when DWAVE_API_TOKEN is set (explicit opt-in — QPU time
costs real money; see router.build_providers). Uses DWaveCliqueSampler: our
QUBO is dense (the budget penalty couples every pair of bits), and the clique
sampler reuses precomputed clique embeddings instead of re-running a minutes-
long minor-embedding search per solve. The reported solve time is QPU access
time, not wall clock; feasible races are ranked by reported solve/access time.

num_reads and spin-reversal-transform count both scale with QUBO size (see
reads_for_vars / srt_for_vars): small baskets stay fast (win the speed race),
large ones trade speed for feasibility via gauge averaging.
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


def srt_for_vars(n_vars: int) -> int:
    """Spin-reversal transforms for a QUBO of n_vars — see DWAVE_SRT_BY_VARS. 0 on
    small/fast problems (keep them quick); more on large ones (gauge averaging buys
    ~1.35× the per-sample feasibility rate plus extra samples past the 1s/job cap)."""
    for max_vars, srt in config.DWAVE_SRT_BY_VARS:
        if n_vars <= max_vars:
            return srt
    return 0


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


_srt_sampler = None


def _get_sampler():
    """Build the clique sampler once (the Leap handshake is slow)."""
    global _sampler
    with _sampler_lock:
        if _sampler is None:
            try:
                from dwave.system import DWaveCliqueSampler
            except ImportError as e:
                raise SolverFailed("dwave-system not installed") from e
            kw = {}
            if config.DWAVE_SOLVER_TOPOLOGY:
                kw["solver"] = {"topology__type": config.DWAVE_SOLVER_TOPOLOGY}
            try:
                _sampler = DWaveCliqueSampler(**kw)
            except Exception as e:
                raise SolverFailed(f"D-Wave unavailable: {e}") from e
        return _sampler


def _get_srt_sampler():
    """Clique sampler wrapped in spin-reversal (gauge) averaging, built once."""
    global _srt_sampler
    base = _get_sampler()  # acquires its own lock first (avoids re-entrant deadlock)
    with _sampler_lock:
        if _srt_sampler is None:
            try:
                from dwave.preprocessing.composites import SpinReversalTransformComposite
            except ImportError as e:
                raise SolverFailed("dwave-preprocessing not installed") from e
            _srt_sampler = SpinReversalTransformComposite(base)
        return _srt_sampler


class DWaveProvider:
    name = "dwave"
    role = "QPU"

    def __init__(self, sampler=None, num_reads: int | None = None) -> None:
        self._sampler = sampler  # injectable for tests
        self._num_reads = num_reads  # None → size-based schedule (reads_for_vars)

    def solve_qubo(
        self, qubo: QuboMatrix, problem: PortfolioProblem, deadline_s: float
    ) -> Solution:
        num_reads = self._num_reads if self._num_reads is not None else reads_for_vars(qubo.n)
        srt = srt_for_vars(qubo.n)
        kwargs = sample_kwargs(num_reads)
        if srt:
            kwargs["num_spin_reversal_transforms"] = srt
        # Real path: use the gauge-averaging composite only when srt>0 (else the plain
        # clique sampler — faster, and num_spin_reversal_transforms isn't a valid param).
        if self._sampler is not None:
            sampler = self._sampler  # injected (tests)
        elif srt:
            sampler = _get_srt_sampler()
        else:
            sampler = _get_sampler()
        t0 = time.perf_counter()
        try:
            response = sampler.sample_qubo(qubo.to_dict(), label="qtw-tradinggame", **kwargs)
        except Exception as e:
            raise SolverFailed(f"D-Wave sampling failed: {e}") from e
        wall = time.perf_counter() - t0

        weights, bits = select_solution(response, qubo, problem)
        qpu_access_us = response.info.get("timing", {}).get("qpu_access_time")
        return Solution(
            weights=weights,
            objective=problem.objective(weights),
            solve_time_s=qpu_access_us / 1e6 if qpu_access_us else wall,
            provider="dwave",
            provider_role="QPU",
            feasible=False,  # set by the router's feasibility gate
            raw_bitstring=bits,
        )

    def solve_qp(self, problem: PortfolioProblem, deadline_s: float) -> Solution:
        raise NotImplementedError("D-Wave solves QUBO, not the continuous QP")
