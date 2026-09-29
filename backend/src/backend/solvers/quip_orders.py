"""Quip testnet orders, run outside the solver race.

A chain order takes over a minute to finalize, so the race returns on the local solvers and
the order runs here instead: one worker thread and one shared solver. Submitting one order at
a time keeps two races from signing with the same account nonce, and reusing the solver
saves a connect and metadata load per order. Whatever an order ends as (solved, timed out
with an order ID, failed) is handed to `on_done`.

At most QUIP_MAX_PENDING_ORDERS orders are outstanding (queued or in flight), so an order
never goes out long after the problem it was built from; `submit` refuses the rest. The
queue lives in memory: the worker is a daemon thread, so shutting down drops queued orders
and abandons an in-flight one instead of holding the process open, and the orders' pending
snapshot rows are marked failed at the next startup (JobStore.fail_pending_results).
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from .. import config
from ..financial.qubo_encoder import encode_qubo
from ..financial.types import PortfolioProblem
from .feasibility import check_feasibility
from .providers.xquad import XquadProvider

log = logging.getLogger(__name__)

PROVIDER = "xquad-quip"
ROLE = "NETWORK"

OnDone = Callable[[dict[str, Any]], None]

_lock = threading.Lock()
_queue: queue.SimpleQueue[tuple[PortfolioProblem, OnDone, Future]] = queue.SimpleQueue()
_outstanding = 0  # queued plus in flight, guarded by _lock
_accepting = True
_worker: threading.Thread | None = None
# Touched only on the worker thread. Dropped after any failure so the next order reconnects.
_provider: XquadProvider | None = None


def pending_result() -> dict[str, Any]:
    """The solver result a race reports while its Quip order is still open."""
    return _result(status="pending", feasible=False)


def skipped_result() -> dict[str, Any]:
    """The solver result for a solve whose order `submit` refused."""
    return _result(
        status="skipped",
        feasible=False,
        error=f"{config.QUIP_MAX_PENDING_ORDERS} Quip orders already pending",
    )


def submit(problem: PortfolioProblem, on_done: OnDone) -> Future | None:
    """Queue one order for `problem`; `on_done` receives its final solver result.

    Returns a future that completes after `on_done` runs, or None, queueing nothing, when
    QUIP_MAX_PENDING_ORDERS orders are already outstanding or the worker is shut down.
    """
    global _outstanding, _worker
    with _lock:
        if not _accepting or _outstanding >= config.QUIP_MAX_PENDING_ORDERS:
            return None
        _outstanding += 1
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="quip-order", daemon=True)
            _worker.start()
    done: Future = Future()
    _queue.put((problem, on_done, done))
    return done


def start() -> None:
    """Accept orders again after `shutdown` (the app lifespan calls this at startup)."""
    global _accepting
    with _lock:
        _accepting = True


def shutdown() -> None:
    """Stop accepting orders and drop the queued ones. An in-flight order is left to the
    daemon worker, which the process abandons on exit."""
    global _accepting, _outstanding
    with _lock:
        _accepting = False
        while True:
            try:
                _problem, _on_done, done = _queue.get_nowait()
            except queue.Empty:
                break
            done.cancel()
            _outstanding -= 1


def _work() -> None:
    global _outstanding
    while True:
        problem, on_done, done = _queue.get()
        try:
            _run(problem, on_done)
        finally:
            with _lock:
                _outstanding -= 1
            done.set_result(None)


def _run(problem: PortfolioProblem, on_done: OnDone) -> None:
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
    try:
        on_done(result)
    except Exception:  # noqa: BLE001 — keep the worker alive; the lost result must be visible
        log.exception(
            "recording quip order result failed order_id=%s status=%s",
            result["orderId"],
            result["status"],
        )


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
