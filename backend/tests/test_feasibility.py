"""feasibility: budget, box, and cardinality checks, each in isolation."""

from __future__ import annotations

import numpy as np

from backend.solvers.feasibility import check_feasibility


def test_feasible_solution_passes():
    weights = np.array([0.5, 0.3, 0.2, 0.0])
    result = check_feasibility(weights, K=3, w_max=0.6)
    assert result.feasible
    assert result.nonzero_count == 3
    assert result.reason == "ok"


def test_budget_violation_detected():
    weights = np.array([0.5, 0.3, 0.1, 0.0])  # sums to 0.9
    result = check_feasibility(weights, K=3, w_max=0.6)
    assert not result.feasible
    assert "budget" in result.reason


def test_box_violation_detected():
    weights = np.array([0.7, 0.2, 0.1, 0.0])  # 0.7 > w_max 0.6
    result = check_feasibility(weights, K=3, w_max=0.6)
    assert not result.feasible
    assert "box" in result.reason


def test_cardinality_violation_detected():
    weights = np.array([0.4, 0.3, 0.2, 0.1])  # 4 nonzero, K=3
    result = check_feasibility(weights, K=3, w_max=0.6)
    assert not result.feasible
    assert "cardinality" in result.reason


def test_negative_weight_is_a_box_violation():
    weights = np.array([0.8, 0.4, -0.2, 0.0])  # sums to 1.0; one negative
    result = check_feasibility(weights, K=2, w_max=0.6)
    assert not result.feasible
    assert "box" in result.reason
