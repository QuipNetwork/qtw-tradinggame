"""Convex weight allocation on a fixed support — the classical half of the hybrid.

Once a selection solver (SA / D-Wave) has chosen which K assets to hold, the weights
are a strictly convex problem the QPU should never touch:

    min  (γ/2)·wᵀΣw − μᵀw      s.t.   Σw = 1,   w_min ≤ w_i ≤ w_max

Σ is a covariance (PSD) ⇒ one global optimum, solved exactly here. This is the same
objective Gurobi minimizes for the full MIQP, restricted to the chosen support.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def optimal_weights(
    mu: np.ndarray,
    Sigma: np.ndarray,
    gamma: float,
    w_min: float,
    w_max: float,
) -> np.ndarray:
    """Optimal long-only weights on the K assets in (mu, Sigma); sums to 1, box-bounded.

    Inputs are already restricted to the chosen support (length K). Assumes the box is
    feasible (K·w_min ≤ 1 ≤ K·w_max), which the slider mapping guarantees.
    """
    mu = np.asarray(mu, dtype=float)
    Sigma = np.asarray(Sigma, dtype=float)
    k = len(mu)
    if k == 0:
        return np.zeros(0)

    def obj(w: np.ndarray) -> float:
        return 0.5 * gamma * w @ Sigma @ w - mu @ w

    def jac(w: np.ndarray) -> np.ndarray:
        return gamma * Sigma @ w - mu

    res = minimize(
        obj,
        np.full(k, 1.0 / k),
        jac=jac,
        method="SLSQP",
        bounds=[(w_min, w_max)] * k,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(k)}],
        options={"maxiter": 200, "ftol": 1e-12},
    )
    return res.x
