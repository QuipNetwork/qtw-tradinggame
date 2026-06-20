"""V0 quality bar: budget + box (+ optional cardinality) feasibility.

Convex mode (cardinality_k None): budget Σw=1 and every weight in [w_min, w_max].
Method 3 mode (cardinality_k set): exactly k held, and the box is *semi-continuous*
— a held weight is in [w_min, w_max] while an unheld weight is 0 (so a 0 weight is
NOT a w_min violation).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config


@dataclass(frozen=True)
class FeasibilityResult:
    feasible: bool
    budget_residual: float  # Σw_i − 1, signed
    box_violation: float  # max violation of the [w_min, w_max] bounds
    reason: str = ""
    held_count: int | None = None  # method3: number of held assets (w > eps)


def check_feasibility(
    weights: np.ndarray,
    w_max: float,
    w_min: float = 0.0,
    eps_budget: float | None = None,
    eps_box: float | None = None,
    cardinality_k: int | None = None,
) -> FeasibilityResult:
    eps_b = eps_budget if eps_budget is not None else config.EPS_BUDGET
    eps_x = eps_box if eps_box is not None else config.EPS_BOX

    budget_res = float(weights.sum() - 1.0)
    upper_v = float(max(0.0, (weights - w_max).max()))

    reasons = []
    held_count: int | None = None
    if cardinality_k is None:
        # Convex: every asset must sit in [w_min, w_max].
        lower_v = float(max(0.0, (w_min - weights).max()))
    else:
        # Semi-continuous: the w_min floor binds only on HELD assets; unheld are 0.
        held = weights > eps_x
        held_count = int(held.sum())
        lower_v = float(max(0.0, (w_min - weights[held]).max())) if held.any() else 0.0
        if held_count != cardinality_k:
            reasons.append(f"cardinality held={held_count} != k={cardinality_k}")
    box_v = max(upper_v, lower_v)

    if abs(budget_res) > eps_b:
        reasons.append(f"budget |Σw-1|={abs(budget_res):.4g} > {eps_b}")
    if box_v > eps_x:
        reasons.append(f"box violation {box_v:.4g} > {eps_x}")

    return FeasibilityResult(
        feasible=not reasons,
        budget_residual=budget_res,
        box_violation=box_v,
        reason="; ".join(reasons) if reasons else "ok",
        held_count=held_count,
    )
