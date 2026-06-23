"""Internal dataclasses for the financial pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def correlation_matrix(sigma: np.ndarray) -> np.ndarray:
    """Pearson correlation ρ from a covariance Σ: ρ = D^{-1/2} Σ D^{-1/2}."""
    d = np.sqrt(np.clip(np.diag(sigma), 1e-12, None))
    return sigma / np.outer(d, d)


@dataclass(frozen=True)
class SliderParams:
    """Physical parameters derived from `SliderValues` via slider_map."""

    gamma: float  # risk aversion (objective coefficient)
    w_max: float  # per-asset cap, relative to the basket (1/n → W_MAX_CEILING)
    w_min: float  # participation floor — every basket asset is held at least this
    rebalance_hours: float | None  # scheduled cadence in hours; None means Off
    # cardinality only (None in convex mode): the optimizer sub-selects exactly
    # cardinality_k of the basket and weights them on an M-unit integer grid.
    cardinality_k: int | None = None
    n_units_M: int | None = None
    u_min_units: int | None = None


@dataclass
class PortfolioProblem:
    """Mean-variance allocation over the player's basket.

    min  (γ/2) wᵀΣw  -  μᵀw    s.t. Σwᵢ = 1, w_min ≤ wᵢ ≤ w_max

    Convex mode (cardinality_k is None): a box-constrained QP — every basket
    asset is held; Gurobi solves it natively, SA/D-Wave solve the bit QUBO.

    cardinality mode (cardinality_k set): a cardinality-constrained, semi-continuous
    MIQP — the optimizer holds exactly cardinality_k of the basket, each weight is
    0 or in [w_min, w_max] on an integer-unit grid (M units, u_min floor). Gurobi
    solves the true MIQP; SA/D-Wave solve the integer-units selection QUBO.

    Every solve is a fresh allocation (no turnover anchor).
    """

    mu: np.ndarray  # shape (N,)
    Sigma: np.ndarray  # shape (N, N), symmetric PSD
    gamma: float
    w_max: float
    asset_tickers: list[str]  # the player's basket (subset of the universe)
    w_min: float = 0.0
    # cardinality only (None → convex mode).
    cardinality_k: int | None = None
    n_units_M: int | None = None
    u_min_units: int | None = None
    # Diversification / frustration reward (β): adds β·Σ_{i<j} ρ_ij·y_i·y_j to the
    # objective (0 = off). See config.CARDINALITY_FRUSTRATION_BETA and encode_penalized.
    frustration_beta: float = 0.0

    @property
    def N(self) -> int:
        return self.mu.shape[0]

    @property
    def is_cardinality(self) -> bool:
        return self.cardinality_k is not None

    def objective(self, weights: np.ndarray) -> float:
        """Mean-variance objective, plus the frustration reward when β > 0."""
        value = 0.5 * self.gamma * weights @ self.Sigma @ weights - self.mu @ weights
        if self.frustration_beta:
            held = (weights > 1e-9).astype(float)
            rho = correlation_matrix(self.Sigma)
            # Σ_{i<j} ρ_ij·y_i·y_j = ½·(yᵀρy − Σ y_i)  (ρ_ii = 1, y binary)
            pair_corr = 0.5 * (held @ rho @ held - held.sum())
            value += self.frustration_beta * pair_corr
        return float(value)

    def __post_init__(self) -> None:
        assert self.Sigma.shape == (self.N, self.N), "Sigma must be (N, N)"
        assert len(self.asset_tickers) == self.N, "asset_tickers length mismatch"
        assert 0 < self.w_max <= 1.0, "w_max must be in (0, 1]"
        assert 0.0 <= self.w_min <= self.w_max, "w_min must be in [0, w_max]"
        # Budget must be reachable across the held set: m·w_min ≤ 1 ≤ m·w_max,
        # where m = N (convex, all held) or cardinality_k (cardinality, k held).
        m = self.N if self.cardinality_k is None else self.cardinality_k
        if self.cardinality_k is not None:
            assert 0 < self.cardinality_k <= self.N, "cardinality_k must be in (0, N]"
        assert m * self.w_min <= 1.0 + 1e-9, "held·w_min must be ≤ 1"
        assert m * self.w_max >= 1.0 - 1e-9, "held·w_max must be ≥ 1"
