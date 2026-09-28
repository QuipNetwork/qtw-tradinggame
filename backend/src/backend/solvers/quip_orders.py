"""Quip testnet orders, run outside the solver race.

A chain order takes over a minute to finalize, so the race returns on the local solvers and
the order runs here instead: one worker thread and one shared solver. Submitting one order at
a time keeps two races from signing with the same account nonce, and reusing the solver
saves a connect and metadata load per order. Nothing abandons an order mid-flight: whatever
the order ends as (solved, timed out with an order ID, failed) is handed to `on_done`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from .. import config
from ..financial.qubo_encoder import encode_qubo
from ..financial.types import PortfolioProblem
from .feasibility import check_feasibility
from .providers.xquad import XquadProvider

log = logging.getLogger(__name__)

PROVIDER = "xquad-quip"
ROLE = "NETWORK"

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quip-order")
# Touched only on the worker thread. Dropped after any failure so the next order reconnects.
_provider: XquadProvider | None = None


def pending_result() -> dict[str, Any]:
    """The solver result a race reports while its Quip order is still open."""
    return _result(status="pending", feasible=False)


def submit(problem: PortfolioProblem, on_done: Callable[[dict[str, Any]], None]) -> Future:
    """Queue one order for `problem`; `on_done` receives its final solver result."""
    return _executor.submit(_run, problem, on_done)


def _run(problem: PortfolioProblem, on_done: Callable[[dict[str, Any]], None]) -> None:
    from xqsa import QuipTimeoutError

    global _provider
    if _provider is None:
        _provider = XquadProvider("quip")
    try:
        solution = _provider.solve_qubo(encode_qubo(problem), problem, config.XQUAD_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — every outcome is recorded, never raised
        _provider = None
        order_id = getattr(exc, "order_id", None)
        log.warning("quip order failed order_id=%s: %s", order_id, exc)
        result = _result(
            status="timeout" if isinstance(exc, QuipTimeoutError) else "failed",
            feasible=False,
            error=str(exc),
            order_id=None if order_id is None else str(order_id),
        )
    else:
        feasible = check_feasibility(
            solution.weights,
            problem.w_max,
            problem.w_min,
            cardinality_k=problem.cardinality_k,
        ).feasible
        result = _result(
            status="feasible" if feasible else "infeasible",
            feasible=feasible,
            solve_time_s=solution.solve_time_s,
            objective=solution.objective,
            order_id=solution.order_id,
        )
    on_done(result)


def _result(
    *,
    status: str,
    feasible: bool,
    solve_time_s: float | None = None,
    objective: float | None = None,
    error: str | None = None,
    order_id: str | None = None,
) -> dict[str, Any]:
    # Same keys as a race's solver-run summary in the job's solve snapshot.
    return {
        "provider": PROVIDER,
        "providerRole": ROLE,
        "status": status,
        "feasible": feasible,
        "solveTime": solve_time_s,
        "raceTime": None,
        "objective": objective,
        "bestObjective": False,
        "error": error,
        "orderId": order_id,
    }
