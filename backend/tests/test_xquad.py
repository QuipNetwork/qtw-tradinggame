"""xquad adapter tests: integer QUBO, backend selection, and sample decoding."""

import argparse
import logging
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import create_app
from backend.api.schemas import AgentConfig, SliderValues
from backend.cli import _build_problem
from backend.financial.basket import TICKERS
from backend.financial.qubo_encoder import encode_qubo
from backend.orchestration.job import run_optimization
from backend.persistence.agents import get_agent_store
from backend.persistence.jobs import get_job_store
from backend.solvers import quip_orders
from backend.solvers.providers.xquad import XquadProvider, selected_backend
from backend.solvers.router import build_providers
from backend.solvers.xquad_model import smoke_xqmx, to_xqmx


def test_model_preserves_combined_off_diagonal(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)
    model, scale = to_xqmx(qubo)
    assert model.size == qubo.n
    for (i, j), coefficient in qubo.to_dict().items():
        value = model.get_linear(i) if i == j else model.get_quadratic(i, j)
        assert value == round(coefficient * scale)


def test_model_rejects_nonfinite(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)
    qubo.Q[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        to_xqmx(qubo)


def test_provider_decodes_xqmx_sample(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)

    class FakeSolver:
        def solve(self, model):
            sample = type(model).binary_sample(model.size)
            for i in range(model.size):
                sample.set_linear(i, 1)
            return SimpleNamespace(sample=sample, timing=0.02, metadata={"order_id": "abc"})

    provider = XquadProvider("dwave-cpu", solver=FakeSolver())
    solution = provider.solve_qubo(qubo, synthetic_problem_3assets, 10)
    assert solution.provider == "xquad-dwave-cpu"
    assert solution.provider_role == "CPU"
    assert len(solution.raw_bitstring) == qubo.n
    assert np.isfinite(solution.objective)
    assert solution.order_id == "abc"


def test_selected_backend_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("XQUAD_BACKEND", raising=False)
    assert selected_backend() is None
    monkeypatch.setenv("XQUAD_BACKEND", "quip")
    assert selected_backend() == "quip"
    monkeypatch.setenv("XQUAD_BACKEND", "invalid")
    with pytest.raises(ValueError, match="XQUAD_BACKEND"):
        selected_backend()


class _FakeSolverQuip:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.network = None

    @classmethod
    def for_network(cls, name, **kwargs):
        solver = cls(**kwargs)
        solver.network = name
        return solver


def _quip_solver(monkeypatch):
    monkeypatch.setitem(sys.modules, "xqsa", SimpleNamespace(SolverQuip=_FakeSolverQuip))
    return XquadProvider("quip")._make_solver()


def test_quip_provider_defaults_to_the_aglais_preset(monkeypatch):
    monkeypatch.delenv("QUIP_RPC_URL", raising=False)
    solver = _quip_solver(monkeypatch)

    assert solver.network == "aglais"
    # The portfolio QUBO is a clique; no registered hardware topology hosts it.
    assert solver.kwargs == {"topology": "native", "timeout": config.XQUAD_TIMEOUT_S}


def test_quip_rpc_url_bypasses_the_preset(monkeypatch):
    # xqsa then reads QUIP_RPC_URL and QUIP_FAUCET_URL itself.
    monkeypatch.setenv("QUIP_RPC_URL", "ws://localhost:20049/rpc")
    solver = _quip_solver(monkeypatch)

    assert solver.network is None
    assert solver.kwargs == {"topology": "native", "timeout": config.XQUAD_TIMEOUT_S}


def test_full_universe_qubo_encodes_as_a_native_quip_order():
    from xqsa.quip_codec import model_to_ising, native_placement

    args = argparse.Namespace(rebalance=50, risk=50, max_position=50, hold_count=8, assets=None)
    qubo = encode_qubo(_build_problem(list(TICKERS), args))
    model, _scale = to_xqmx(qubo)
    topology, mapping = native_placement(model)

    job = model_to_ising(model, topology, mapping=mapping)  # raises on any i32 overflow

    assert len(job.h_values) == len(TICKERS)
    assert len(job.j_values) == len(TICKERS) * (len(TICKERS) - 1) // 2


def test_race_selects_xquad_instead_of_direct_dwave(monkeypatch):
    monkeypatch.setenv("DWAVE_API_TOKEN", "never-used")
    monkeypatch.setenv("XQUAD_BACKEND", "dwave-qpu")
    assert [p.name for p in build_providers() if p.role == "QPU"] == ["xquad-dwave-qpu"]
    assert all(p.name != "dwave" for p in build_providers())
    assert all(p.name != "xquad-dwave-qpu" for p in build_providers(include_qpu=False))


def test_quip_orders_run_outside_the_race(monkeypatch):
    monkeypatch.setenv("DWAVE_API_TOKEN", "never-used")
    monkeypatch.setenv("XQUAD_BACKEND", "quip")
    assert {p.role for p in build_providers()} == {"CPU"}


def test_local_cpu_does_not_require_remote_admission(monkeypatch):
    monkeypatch.setenv("XQUAD_BACKEND", "dwave-cpu")
    assert "xquad-dwave-cpu" in [p.name for p in build_providers(include_qpu=False)]


def test_invalid_sample_is_rejected(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)

    class InvalidSample:
        size = qubo.n

        @staticmethod
        def get_linear(index):
            return 256 if index == 0 else 0

    class FakeSolver:
        def solve(self, model):
            return SimpleNamespace(sample=InvalidSample())

    with pytest.raises(ValueError, match="non-binary"):
        XquadProvider("dwave-cpu", solver=FakeSolver()).solve_qubo(
            qubo, synthetic_problem_3assets, 10
        )


def test_smoke_model_fits_one_hardware_edge():
    model = smoke_xqmx()

    assert model.size == 2
    assert model.get_linear(0) == 0
    assert model.get_linear(1) == 0
    assert model.get_quadratic(0, 1) == 1


class _FakeQuipOrder:
    """Solves on the calling thread like SolverQuip.solve, selecting every variable.

    With `release`, each solve blocks until the event is set, holding the worker busy."""

    def __init__(self, order_id=92, error=None, release=None):
        self.order_id = order_id
        self.error = error
        self.release = release
        self.calls = 0

    def solve(self, model):
        self.calls += 1
        if self.release is not None:
            assert self.release.wait(10)
        if self.error is not None:
            raise self.error
        sample = type(model).binary_sample(model.size)
        for i in range(model.size):
            sample.set_linear(i, 1)
        return SimpleNamespace(sample=sample, metadata={"order_id": self.order_id})


def test_quip_order_reports_its_final_result(monkeypatch, synthetic_problem_3assets):
    order = _FakeQuipOrder()
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=order))
    results = []

    quip_orders.submit(synthetic_problem_3assets, results.append).result(timeout=10)

    [result] = results
    assert result["provider"] == "xquad-quip"
    assert result["providerRole"] == "NETWORK"
    assert result["status"] in ("feasible", "infeasible")
    assert result["orderId"] == "92"
    assert result["objective"] is not None and result["solveTime"] is not None


def test_quip_orders_share_one_solver(monkeypatch, synthetic_problem_3assets):
    order = _FakeQuipOrder()
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=order))
    futures = [quip_orders.submit(synthetic_problem_3assets, lambda _: None) for _ in range(3)]
    for future in futures:
        future.result(timeout=10)
    assert order.calls == 3


def test_quip_order_timeout_keeps_its_order_id(monkeypatch, synthetic_problem_3assets):
    from xqsa import QuipTimeoutError

    order = _FakeQuipOrder(error=QuipTimeoutError(93))
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=order))
    results = []

    quip_orders.submit(synthetic_problem_3assets, results.append).result(timeout=10)

    [result] = results
    assert result["status"] == "timeout"
    assert result["orderId"] == "93"
    assert result["feasible"] is False
    assert quip_orders._provider is None  # the next order reconnects


def test_quip_orders_are_capped_while_pending(monkeypatch, synthetic_problem_3assets):
    monkeypatch.setattr(config, "QUIP_MAX_PENDING_ORDERS", 2)
    release = threading.Event()
    order = _FakeQuipOrder(release=release)
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=order))

    accepted = [quip_orders.submit(synthetic_problem_3assets, lambda _: None) for _ in range(2)]
    refused = quip_orders.submit(synthetic_problem_3assets, lambda _: None)
    release.set()
    for future in accepted:
        future.result(timeout=10)

    assert refused is None
    assert order.calls == 2
    assert quip_orders.submit(synthetic_problem_3assets, lambda _: None).result(timeout=10) is None


def test_shutdown_drops_queued_orders_and_refuses_new_ones(monkeypatch, synthetic_problem_3assets):
    release = threading.Event()
    order = _FakeQuipOrder(release=release)
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=order))
    in_flight = quip_orders.submit(synthetic_problem_3assets, lambda _: None)
    deadline = time.monotonic() + 10
    while order.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    queued = quip_orders.submit(synthetic_problem_3assets, lambda _: None)

    try:
        quip_orders.shutdown()
        assert queued.cancelled()
        assert quip_orders.submit(synthetic_problem_3assets, lambda _: None) is None
    finally:
        quip_orders.start()
        release.set()
    in_flight.result(timeout=10)
    assert order.calls == 1
    assert quip_orders.submit(synthetic_problem_3assets, lambda _: None).result(timeout=10) is None


def test_a_failing_result_callback_is_logged(monkeypatch, caplog, synthetic_problem_3assets):
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=_FakeQuipOrder()))

    def lost(_result):
        raise KeyError("no solve snapshot")

    with caplog.at_level(logging.ERROR, logger="backend.solvers.quip_orders"):
        quip_orders.submit(synthetic_problem_3assets, lost).result(timeout=10)

    assert "recording quip order result failed order_id=92" in caplog.text
    assert "no solve snapshot" in caplog.text  # the traceback is logged
    results = []
    quip_orders.submit(synthetic_problem_3assets, results.append).result(timeout=10)
    assert [r["orderId"] for r in results] == ["92"]  # the worker survives


def _quip_agent():
    return get_agent_store().create(
        AgentConfig(
            name="Quanta",
            email="q@example.com",
            sliders=SliderValues(
                rebalanceFrequency=50, riskPreference=50, maxPositionSize=50, holdCount=5
            ),
            assets=list(TICKERS[:15]),
        ),
        bankroll=10_000.0,
    )


def _quip_row(result):
    return next(r for r in result.solver_results if r.provider_type == "NETWORK")


def _snapshot_quip_result():
    [snapshot] = get_job_store().solve_snapshots()
    return next(r for r in snapshot["solver_results"] if r["provider"] == "xquad-quip")


def test_optimize_returns_before_the_quip_order_finalizes(monkeypatch):
    monkeypatch.setenv("XQUAD_BACKEND", "quip")
    monkeypatch.setattr(config, "GUROBI_IN_RACE", False)
    monkeypatch.setattr(quip_orders, "_provider", XquadProvider("quip", solver=_FakeQuipOrder()))

    result = run_optimization(_quip_agent().id).result

    assert result.provider == "Simulated Annealing"
    quip = _quip_row(result)
    assert (quip.status, quip.order_id, quip.solve_time) == ("pending", None, None)
    deadline = time.monotonic() + 10
    while _snapshot_quip_result()["status"] == "pending" and time.monotonic() < deadline:
        time.sleep(0.05)
    final = _snapshot_quip_result()
    assert final["status"] in ("feasible", "infeasible")
    assert final["orderId"] == "92"


def test_optimize_records_a_skipped_order_when_too_many_are_pending(monkeypatch):
    monkeypatch.setenv("XQUAD_BACKEND", "quip")
    monkeypatch.setattr(config, "GUROBI_IN_RACE", False)
    monkeypatch.setattr(quip_orders, "submit", lambda problem, on_done: None)

    quip = _quip_row(run_optimization(_quip_agent().id).result)

    assert quip.status == "skipped"
    assert "already pending" in quip.error
    assert _snapshot_quip_result()["status"] == "skipped"


def test_scheduled_rebalances_propose_no_quip_order(monkeypatch):
    monkeypatch.setenv("XQUAD_BACKEND", "quip")
    monkeypatch.setattr(config, "GUROBI_IN_RACE", False)
    submitted = []
    monkeypatch.setattr(quip_orders, "submit", lambda *args: submitted.append(args))
    agent = _quip_agent()

    result = run_optimization(agent.id, source="scheduled").result

    assert submitted == []
    assert all(r.provider_type != "NETWORK" for r in result.solver_results)
    assert result.qpu_budget.used == 0  # no paid order, no admission budget spent


def test_startup_fails_quip_results_left_pending(monkeypatch):
    jobs = get_job_store()
    jobs.record_solve_snapshot(
        job_id="job1",
        agent_id="agent1",
        sliders={},
        assets=["BTC"],
        portfolio=[],
        holdings_units={},
        solver_results=[{"provider": "sa", "status": "winner"}, quip_orders.pending_result()],
        winner_provider="sa",
    )

    with TestClient(create_app()):
        pass

    final = _snapshot_quip_result()
    assert final["status"] == "failed"
    assert "restarted" in final["error"]
