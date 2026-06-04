"""Internal dataclasses for the financial pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SliderParams:
    """Physical parameters derived from `SliderValues` via slider_map."""

    gamma: float  # risk aversion (objective coefficient)
    w_max: float  # per-asset cap
    w_min: float  # min size of a selected position (enforces exactly-K)
    tau_hours: int  # μ-window in hours (Holding Style slider)
    K: int  # cardinality (exactly-K)
    lambda_t: float  # turnover penalty weight (0 in V0)


@dataclass
class MIQPProblem:
    """Mean-variance mean-variance MIQP — native Gurobi input form.

    min  (γ/2) wᵀΣw  -  μᵀw  +  λ_t ‖w - w_ref‖²
    s.t. Σwᵢ = 1
         w_min · yᵢ ≤ wᵢ ≤ w_max · yᵢ   (coupling + min position → exactly-K)
         Σyᵢ = K                          (cardinality)
         yᵢ ∈ {0,1}, wᵢ ∈ ℝ
    """

    mu: np.ndarray  # shape (N,)
    Sigma: np.ndarray  # shape (N, N), symmetric PSD
    gamma: float
    lambda_t: float
    w_ref: np.ndarray  # shape (N,) — zero on first solve, w_prev on retune
    w_max: float
    K: int
    asset_tickers: list[str]
    w_min: float = 0.0  # min size of a selected position; 0 disables the floor

    @property
    def N(self) -> int:
        return self.mu.shape[0]

    def __post_init__(self) -> None:
        assert self.Sigma.shape == (self.N, self.N), "Sigma must be (N, N)"
        assert self.w_ref.shape == (self.N,), "w_ref must be (N,)"
        assert len(self.asset_tickers) == self.N, "asset_tickers length mismatch"
        assert 0 < self.K <= self.N, "K must be in [1, N]"
        assert 0 < self.w_max <= 1.0, "w_max must be in (0, 1]"
        assert 0.0 <= self.w_min <= self.w_max, "w_min must be in [0, w_max]"
        assert self.K * self.w_min <= 1.0 + 1e-9, "K·w_min must be ≤ 1 (budget feasible)"
