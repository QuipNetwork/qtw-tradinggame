"""optimal_weights: the convex weight QP always returns a feasible portfolio (Σw=1, box)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.financial.weighting import optimal_weights


def _feasible(w: np.ndarray, w_min: float, w_max: float) -> bool:
    return bool(
        abs(w.sum() - 1.0) < 1e-6 and (w >= w_min - 1e-6).all() and (w <= w_max + 1e-6).all()
    )


@pytest.mark.parametrize(
    "k,w_min,w_max",
    [(3, 0.02, 0.6), (5, 1 / 32, 0.5), (8, 0.02, 0.5), (2, 0.1, 0.9), (6, 0.05, 0.25)],
)
def test_optimal_weights_is_always_feasible(k: int, w_min: float, w_max: float):
    rng = np.random.default_rng(0)
    for _ in range(20):
        A = rng.normal(size=(k, k))
        Sigma = A @ A.T / k + np.eye(k) * 0.01
        mu = rng.uniform(-0.02, 0.05, size=k)
        w = optimal_weights(mu, Sigma, gamma=float(rng.uniform(0.5, 4.0)), w_min=w_min, w_max=w_max)
        assert len(w) == k
        assert _feasible(w, w_min, w_max), (w, float(w.sum()))


def test_optimal_weights_handles_near_singular_covariance():
    # Rank-deficient / near-singular Σ (e.g. duplicated assets) must still yield a feasible point.
    k = 5
    base = np.array([1.0, 1.0, 0.0, 0.0, 0.0])
    sigma = np.outer(base, base) + np.eye(k) * 1e-10
    w = optimal_weights(np.full(k, 0.01), sigma, gamma=2.0, w_min=0.05, w_max=0.5)
    assert _feasible(w, 0.05, 0.5)


def test_optimal_weights_tight_box_forces_equal_weight():
    # w_max = 1/k leaves only the equal-weight point feasible — must return ~1/k.
    k = 4
    w = optimal_weights(np.full(k, 0.03), np.eye(k), gamma=1.0, w_min=0.0, w_max=1.0 / k)
    assert _feasible(w, 0.0, 1.0 / k)
    assert np.allclose(w, 1.0 / k, atol=1e-6)


def test_optimal_weights_empty_support():
    assert optimal_weights(
        np.array([]), np.zeros((0, 0)), gamma=1.0, w_min=0.0, w_max=1.0
    ).shape == (0,)
