"""Shared solver dataclasses — what providers consume and produce."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

ProviderName = Literal["dwave", "sa", "gurobi"]
ProviderRole = Literal["QPU", "CPU"]


@dataclass(frozen=True)
class DecodeMeta:
    """Information needed to decode a QUBO bitstring back to portfolio weights.

    scheme="convex" (default): bit layout (i-major) p = i*b + k holds weight bit
    x_{i,k}; every asset carries w_min plus a bit-encoded increment spanning
    [w_min, w_max] — no indicator block (basket decides participation).

    scheme="penalized": layout is [y_0..y_{n-1}, x_{0,0}..x_{n-1,b-1}] — n select
    bits then n·b increment bits; held weight = (u_min + Σ 2^k x_{i,k}) / M units.

    scheme="select" (C2): just n selection bits x_i (hold asset i?). Weights are NOT
    encoded — a greedy projector + convex QP set them classically (see solvers.sampling,
    financial.projection, financial.weighting). The QUBO carries only the objective + β.
    """

    n_assets: int
    bits_per_asset: int
    w_max: float
    asset_tickers: list[str]
    w_min: float = 0.0
    scheme: Literal["convex", "penalized", "select"] = "convex"
    n_units_M: int | None = None  # cardinality: integer-unit grid size (2^m)
    u_min_units: int | None = None  # cardinality: floor units per held asset
    increment_bits: int | None = None  # cardinality: b increment bits per asset

    @property
    def n_total_bits(self) -> int:
        if self.scheme == "penalized":
            return self.n_assets * (1 + self.increment_bits)
        if self.scheme == "select":
            return self.n_assets  # one selection bit per asset (weights set classically)
        return self.n_assets * self.bits_per_asset

    @property
    def weight_coef(self) -> float:
        """Per-bit increment above w_min (convex bits span [w_min, w_max])."""
        return (self.w_max - self.w_min) / (2**self.bits_per_asset - 1)

    def y(self, i: int) -> int:
        """cardinality: index of asset i's select bit."""
        return i

    def x(self, i: int, k: int) -> int:
        """cardinality: index of asset i's k-th increment bit."""
        return self.n_assets + i * self.increment_bits + k


@dataclass
class QuboMatrix:
    """Symmetric QUBO: minimize xᵀQx subject to x ∈ {0,1}ⁿ."""

    Q: np.ndarray  # symmetric, shape (n, n)
    decode_meta: DecodeMeta

    @property
    def n(self) -> int:
        return self.Q.shape[0]

    def to_dict(self) -> dict[tuple[int, int], float]:
        """Upper-triangle dict form for Ocean samplers (combines symmetric halves)."""
        qdict: dict[tuple[int, int], float] = {}
        for i in range(self.n):
            qdict[(i, i)] = float(self.Q[i, i])
            for j in range(i + 1, self.n):
                v = float(self.Q[i, j] + self.Q[j, i])
                if v != 0.0:
                    qdict[(i, j)] = v
        return qdict


@dataclass
class Solution:
    """A solver's output."""

    weights: np.ndarray  # shape (N,), should sum to ~1 if feasible
    objective: float  # the mean-variance objective value at these weights
    solve_time_s: float  # wall-clock time spent in solver
    provider: ProviderName
    provider_role: ProviderRole
    feasible: bool  # set by feasibility checker, not the provider itself
    raw_bitstring: np.ndarray | None = None  # for QUBO solvers; None for Gurobi QP


@dataclass
class ProviderProvenance:
    """Audit metadata preserved per job (currently lost at the API boundary,
    but persisted in jobs.py for the audit log).
    """

    provider: ProviderName
    provider_role: ProviderRole
    q_hash: str  # SHA256 of QUBO matrix (for race-result audit)
    deadline_s: float
    solve_time_s: float
    feasible: bool


class SolverFailed(Exception):
    """Raised when a solver returns no usable result before its deadline."""

    pass
