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

    Bit layout (i-major):
    - positions 0 .. N*b - 1: weight bits x_{i,k} where i = pos // b, k = pos % b
    - positions N*b .. N*(b+1) - 1: cardinality indicators y_i
    """

    n_assets: int
    bits_per_asset: int
    w_max: float
    asset_tickers: list[str]
    w_min: float = 0.0  # min size of a selected position; bits span [w_min, w_max]

    @property
    def n_weight_bits(self) -> int:
        return self.n_assets * self.bits_per_asset

    @property
    def n_total_bits(self) -> int:
        return self.n_assets * (self.bits_per_asset + 1)

    @property
    def weight_coef(self) -> float:
        """Per-bit increment above w_min (so bits encode the [w_min, w_max] span)."""
        return (self.w_max - self.w_min) / (2**self.bits_per_asset - 1)


@dataclass
class QuboMatrix:
    """Symmetric QUBO: minimize xᵀQx subject to x ∈ {0,1}ⁿ."""

    Q: np.ndarray  # symmetric, shape (n, n)
    decode_meta: DecodeMeta

    @property
    def n(self) -> int:
        return self.Q.shape[0]


@dataclass
class Solution:
    """A solver's output."""

    weights: np.ndarray  # shape (N,), should sum to ~1 if feasible
    objective: float  # the mean-variance objective value at these weights
    solve_time_s: float  # wall-clock time spent in solver
    provider: ProviderName
    provider_role: ProviderRole
    feasible: bool  # set by feasibility checker, not the provider itself
    raw_bitstring: np.ndarray | None = None  # for QUBO solvers; None for Gurobi MIQP


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
