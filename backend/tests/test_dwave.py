"""D-Wave provider: decode path via an injected sampler, and the token gate."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.qubo_encoder import encode_qubo
from backend.solvers.providers.dwave import DWaveProvider
from backend.solvers.router import build_providers


class FakeResponse:
    def __init__(self, sample: dict[int, int], qpu_access_us: float):
        self.first = type("Best", (), {"sample": sample})()
        self.info = {"timing": {"qpu_access_time": qpu_access_us}}


class FakeSampler:
    def __init__(self, bits: np.ndarray, qpu_access_us: float = 16_000.0):
        self._bits = bits
        self._qpu_access_us = qpu_access_us
        self.last_qubo: dict | None = None

    def sample_qubo(self, qdict, **kwargs):
        self.last_qubo = qdict
        return FakeResponse({i: int(b) for i, b in enumerate(self._bits)}, self._qpu_access_us)


def test_solve_qubo_decodes_and_reports_qpu_time(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)
    # levels [8, 8, 5] sum exactly to 1.0 for w_min=0.1, w_max=0.6, b=4
    bits = np.zeros(qubo.n, dtype=np.int8)
    for i, level in enumerate([8, 8, 5]):
        for k in range(4):
            bits[i * 4 + k] = (level >> k) & 1

    sampler = FakeSampler(bits)
    solution = DWaveProvider(sampler=sampler).solve_qubo(
        qubo, synthetic_problem_3assets, deadline_s=2.0
    )

    assert solution.provider == "dwave"
    assert solution.provider_role == "QPU"
    assert solution.weights.sum() == pytest.approx(1.0)
    assert solution.solve_time_s == pytest.approx(0.016)  # QPU access, not wall clock
    assert sampler.last_qubo == qubo.to_dict()


def test_race_field_requires_a_leap_token(monkeypatch):
    monkeypatch.delenv("DWAVE_API_TOKEN", raising=False)
    assert [p.name for p in build_providers()] == ["gurobi", "sa"]

    monkeypatch.setenv("DWAVE_API_TOKEN", "token")
    assert [p.name for p in build_providers()] == ["gurobi", "sa", "dwave"]
