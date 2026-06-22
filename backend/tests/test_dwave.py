"""D-Wave provider: decode path, best-of-reads selection, the token gate."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.qubo_encoder import encode_qubo
from backend.solvers.providers.dwave import DWaveProvider
from backend.solvers.router import build_providers


def _bits_for_levels(levels: list[int], n_bits: int, b: int = 4) -> np.ndarray:
    bits = np.zeros(n_bits, dtype=np.int8)
    for i, level in enumerate(levels):
        for k in range(b):
            bits[i * b + k] = (level >> k) & 1
    return bits


class FakeResponse:
    """Minimal stand-in for a dimod SampleSet (energy-ascending samples)."""

    def __init__(self, samples: list[dict[int, int]], qpu_access_us: float):
        self._samples = samples
        self.first = type("Best", (), {"sample": samples[0]})()
        self.info = {"timing": {"qpu_access_time": qpu_access_us}}

    def samples(self):
        return self._samples


class FakeSampler:
    def __init__(self, samples: list[dict[int, int]], qpu_access_us: float = 16_000.0):
        self._samples = samples
        self._qpu_access_us = qpu_access_us
        self.last_qubo: dict | None = None
        self.last_kwargs: dict | None = None

    def sample_qubo(self, qdict, **kwargs):
        self.last_qubo = qdict
        self.last_kwargs = kwargs
        return FakeResponse(self._samples, self._qpu_access_us)


def _as_sample(bits: np.ndarray) -> dict[int, int]:
    return {i: int(b) for i, b in enumerate(bits)}


def test_solve_qubo_decodes_and_reports_qpu_time(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)
    # levels [8, 8, 5] sum exactly to 1.0 for w_min=0.1, w_max=0.6, b=4
    bits = _bits_for_levels([8, 8, 5], qubo.n)

    sampler = FakeSampler([_as_sample(bits)])
    solution = DWaveProvider(sampler=sampler).solve_qubo(
        qubo, synthetic_problem_3assets, deadline_s=2.0
    )

    assert solution.provider == "dwave"
    assert solution.provider_role == "QPU"
    assert solution.weights.sum() == pytest.approx(1.0)
    assert solution.solve_time_s == pytest.approx(0.016)  # QPU access, not wall clock
    assert sampler.last_qubo == qubo.to_dict()


def test_best_feasible_read_beats_lowest_energy(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)
    # lowest-energy sample badly violates the budget; a later read is feasible
    infeasible = _bits_for_levels([15, 15, 15], qubo.n)  # Σw = 1.8
    feasible = _bits_for_levels([8, 8, 5], qubo.n)  # Σw = 1.0

    sampler = FakeSampler([_as_sample(infeasible), _as_sample(feasible)])
    solution = DWaveProvider(sampler=sampler).solve_qubo(
        qubo, synthetic_problem_3assets, deadline_s=2.0
    )

    assert solution.weights.sum() == pytest.approx(1.0)
    assert np.array_equal(solution.raw_bitstring, feasible)


def test_reads_scale_with_basket_size():
    from backend import config
    from backend.solvers.sampling import reads_for_vars

    # Test the lookup LOGIC, not the literal table (which re-tunes): a 500 floor (matches
    # SA's baseline), boundary-inclusive first-match, and reads never decrease with size.
    assert reads_for_vars(48) == config.DWAVE_READS_BY_VARS[0][1]  # first tier (floor 500)
    assert reads_for_vars(49) > reads_for_vars(48)  # next tier up
    reads = [reads_for_vars(n) for n in (12, 48, 49, 72, 84, 140)]
    assert reads == sorted(reads)  # monotonic non-decreasing
    assert min(reads) == 500  # floored at SA's 500 baseline (apples-to-apples)


def test_srt_disabled_by_default():
    # Deliberately off for every size (client-side composite = N cloud jobs → blows the
    # wall-clock deadline). Plumbing kept for offline use; see DWAVE_SRT_BY_VARS.
    from backend.solvers.providers.dwave import srt_for_vars

    assert srt_for_vars(36) == 0 and srt_for_vars(140) == 0


def test_srt_forwarded_to_sampler_when_enabled(monkeypatch, synthetic_problem_3assets):
    # When SRT is config-enabled, solve_qubo must forward num_spin_reversal_transforms
    # to the sampler — covers the otherwise-disabled gauge-averaging path.
    from backend.solvers.providers import dwave as dwave_mod

    monkeypatch.setattr(dwave_mod, "srt_for_vars", lambda n: 4)
    qubo = encode_qubo(synthetic_problem_3assets)
    bits = _bits_for_levels([8, 8, 5], qubo.n)
    sampler = FakeSampler([_as_sample(bits)])
    dwave_mod.DWaveProvider(sampler=sampler).solve_qubo(
        qubo, synthetic_problem_3assets, deadline_s=2.0
    )
    assert sampler.last_kwargs["num_spin_reversal_transforms"] == 4


def test_solve_qubo_uses_size_based_reads(synthetic_problem_3assets):
    qubo = encode_qubo(synthetic_problem_3assets)  # 3 assets × b4 = 12 vars → floor tier
    bits = _bits_for_levels([8, 8, 5], qubo.n)
    sampler = FakeSampler([_as_sample(bits)])
    DWaveProvider(sampler=sampler).solve_qubo(qubo, synthetic_problem_3assets, deadline_s=2.0)
    assert sampler.last_kwargs["num_reads"] == 500  # 12v → floored at 500


def test_sa_reads_match_dwave_above_baseline(monkeypatch, synthetic_problem_3assets):
    # apples-to-apples: SA matches D-Wave's read budget when it exceeds the 500 baseline;
    # small problems keep the 500 floor (so SA is never starved of restarts).
    from backend.solvers.providers import sa as sa_mod

    qubo = encode_qubo(synthetic_problem_3assets)
    bits = _bits_for_levels([8, 8, 5], qubo.n)
    s1 = FakeSampler([_as_sample(bits)])
    sa_mod.SAProvider(sampler=s1).solve_qubo(qubo, synthetic_problem_3assets, deadline_s=2.0)
    assert s1.last_kwargs["num_reads"] == 500  # reads_for_vars(12)=150 < 500 → floor

    monkeypatch.setattr(sa_mod, "reads_for_vars", lambda n: 1000)
    s2 = FakeSampler([_as_sample(bits)])
    sa_mod.SAProvider(sampler=s2).solve_qubo(qubo, synthetic_problem_3assets, deadline_s=2.0)
    assert s2.last_kwargs["num_reads"] == 1000  # D-Wave schedule > 500 → SA matches


def _m3_sample(units: dict[int, int], meta) -> dict[int, int]:
    sample = dict.fromkeys(range(meta.n_total_bits), 0)
    for i, u in units.items():
        sample[meta.y(i)] = 1
        inc = u - meta.u_min_units
        for k in range(meta.increment_bits):
            sample[meta.x(i, k)] = (inc >> k) & 1
    return sample


def test_cardinality_decodes_units_and_respects_cardinality():
    from backend.financial.qubo_encoder import encode_penalized
    from backend.financial.types import PortfolioProblem

    prob = PortfolioProblem(
        mu=np.array([0.03, 0.04, 0.01]),
        Sigma=np.eye(3) * 0.04,
        gamma=2.0,
        w_max=0.6,
        w_min=1 / 32,
        asset_tickers=["A", "B", "C"],
        cardinality_k=2,
        n_units_M=32,
        u_min_units=1,
    )
    qubo = encode_penalized(prob)
    sample = _m3_sample({0: 16, 1: 16}, qubo.decode_meta)  # 0.5 / 0.5, exactly 2 held
    solution = DWaveProvider(sampler=FakeSampler([sample])).solve_qubo(qubo, prob, deadline_s=2.0)

    assert solution.weights.sum() == pytest.approx(1.0)  # exact (integer units)
    assert int((solution.weights > 1e-6).sum()) == 2
    assert solution.weights == pytest.approx([0.5, 0.5, 0.0])


def test_race_field_requires_a_leap_token(monkeypatch):
    monkeypatch.delenv("DWAVE_API_TOKEN", raising=False)
    assert [p.name for p in build_providers()] == ["gurobi", "sa"]

    monkeypatch.setenv("DWAVE_API_TOKEN", "token")
    assert [p.name for p in build_providers()] == ["gurobi", "sa", "dwave"]
    assert [p.name for p in build_providers(include_qpu=False)] == ["gurobi", "sa"]


def test_production_race_excludes_gurobi(monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "GUROBI_IN_RACE", False)
    monkeypatch.setenv("DWAVE_API_TOKEN", "token")
    assert [p.name for p in build_providers()] == ["sa", "dwave"]
