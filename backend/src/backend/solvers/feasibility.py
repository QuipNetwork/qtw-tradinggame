"""V0 quality bar: feasibility-only.

Each solver returns weights. The router accepts the first solution whose
weights satisfy:
  - budget:      |Σ w_i - 1|       < EPS_BUDGET
  - box:         w_i ≤ w_max + EPS_BOX     for all i
                 w_i ≥ 0                    for all i
  - cardinality: |{ i : w_i > tol }| == K

Returns a dataclass with the boolean and which constraint failed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config


@dataclass(frozen=True)
class FeasibilityResult:
    feasible: bool
    budget_residual: float  # Σw_i - 1  (signed)
    box_violation: float  # max(0, max(w_i - w_max), max(-w_i))
    nonzero_count: int  # number of w_i > tol
    expected_K: int
    reason: str = ""


def check_feasibility(
    weights: np.ndarray,
    K: int,
    w_max: float,
    zero_tol: float | None = None,
    eps_budget: float | None = None,
    eps_box: float | None = None,
) -> FeasibilityResult:
    """Validate weights against the three constraint classes."""
    eps_b = eps_budget if eps_budget is not None else config.EPS_BUDGET
    eps_x = eps_box if eps_box is not None else config.EPS_BOX
    # Anything below w_max / 10⁴ is considered "zero" for cardinality counting.
    tol = zero_tol if zero_tol is not None else w_max * 1e-4

    budget_res = float(weights.sum() - 1.0)
    over_cap = float(max(0.0, (weights - w_max).max()))
    under_zero = float(max(0.0, (-weights).max()))
    box_v = max(over_cap, under_zero)
    nonzero = int((weights > tol).sum())

    reasons = []
    if abs(budget_res) > eps_b:
        reasons.append(f"budget |Σw-1|={abs(budget_res):.4g} > {eps_b}")
    if box_v > eps_x:
        reasons.append(f"box violation {box_v:.4g} > {eps_x}")
    if nonzero != K:
        reasons.append(f"cardinality {nonzero} != K={K}")

    return FeasibilityResult(
        feasible=not reasons,
        budget_residual=budget_res,
        box_violation=box_v,
        nonzero_count=nonzero,
        expected_K=K,
        reason="; ".join(reasons) if reasons else "ok",
    )
