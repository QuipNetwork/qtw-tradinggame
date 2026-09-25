"""xquad adapter tests: integer QUBO, backend selection, and sample decoding."""

import asyncio
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from backend.api.routes import routing_stats
from backend.financial.qubo_encoder import encode_qubo
from backend.persistence.jobs import get_job_store
from backend.solvers.providers.xquad import XquadProvider, selected_backend
from backend.solvers.router import build_providers
from backend.solvers.types import ProviderProvenance
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


def _fake_quip_solver(monkeypatch):
    def fake_quip(**kwargs):
        return SimpleNamespace(**kwargs)

    fake_xqsa = SimpleNamespace(
        SolverDWaveCPU=object,
        SolverDWaveQPU=object,
        SolverQuip=fake_quip,
    )
    monkeypatch.setitem(sys.modules, "xqsa", fake_xqsa)
    return XquadProvider("quip")._make_solver(30)


def test_quip_provider_defaults_to_public_aglais_rpc(monkeypatch):
    solver = _fake_quip_solver(monkeypatch)

    assert solver.url == "wss://bootnode-1.aglais.quip.network:20049/rpc"
    assert solver.faucet == "https://faucet.aglais.quip.network"


def test_quip_provider_submits_the_dense_qubo_over_its_own_graph(monkeypatch):
    # The portfolio QUBO is a clique; no registered hardware topology hosts it.
    assert _fake_quip_solver(monkeypatch).topology == "native"


def test_custom_quip_rpc_never_inherits_the_aglais_faucet(monkeypatch):
    import importlib

    from backend import config

    monkeypatch.setenv("QUIP_RPC_URL", "ws://localhost:20049/rpc")
    monkeypatch.delenv("QUIP_FAUCET_URL", raising=False)
    try:
        assert importlib.reload(config).QUIP_FAUCET_URL is None
        monkeypatch.setenv("QUIP_FAUCET_URL", "http://localhost:20049/api/faucet")
        assert importlib.reload(config).QUIP_FAUCET_URL == "http://localhost:20049/api/faucet"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_race_selects_xquad_instead_of_direct_dwave(monkeypatch):
    monkeypatch.setenv("DWAVE_API_TOKEN", "never-used")
    monkeypatch.setenv("XQUAD_BACKEND", "dwave-qpu")
    assert [p.name for p in build_providers() if p.role == "QPU"] == ["xquad-dwave-qpu"]
    assert all(p.name != "dwave" for p in build_providers())
    assert all(p.name != "xquad-dwave-qpu" for p in build_providers(include_qpu=False))


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


def test_network_wins_are_not_reported_as_qpu_wins():
    get_job_store().record(
        "agent",
        ProviderProvenance(
            provider="xquad-quip",
            provider_role="NETWORK",
            q_hash="hash",
            deadline_s=120,
            solve_time_s=1,
            feasible=True,
        ),
    )
    stats = asyncio.run(routing_stats())
    assert stats.network_wins == 1
    assert stats.network_pct == 100
    assert stats.qpu_wins == stats.cpu_wins == 0
