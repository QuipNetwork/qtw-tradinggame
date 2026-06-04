"""Gurobi MIQP solver — native form, no QUBO encoding.

Two roles:
 1. One of three racing solvers under the 'CPU' provider label.
 2. Offline oracle that validates QUBO penalty weights and gives a reference
    optimum for D-Wave/SA solutions to be checked against.

`gurobipy` is a lazy import so the rest of the codebase works without a Gurobi
install. Pip's `gurobipy` includes a size-limited trial license; 60 binary +
15 continuous variables comfortably fits.
"""

from __future__ import annotations

import time

import numpy as np

from ...financial.types import MIQPProblem
from ..types import QuboMatrix, Solution, SolverFailed


class GurobiProvider:
    name = "gurobi"
    role = "CPU"

    def solve_miqp(self, miqp: MIQPProblem, deadline_s: float) -> Solution:
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as e:
            raise SolverFailed("gurobipy not installed") from e

        N = miqp.N
        env = gp.Env(empty=True)
        env.setParam("OutputFlag", 0)
        env.start()
        model = gp.Model("portfolio", env=env)
        model.setParam("TimeLimit", deadline_s)

        w = model.addVars(N, vtype=GRB.CONTINUOUS, lb=0.0, ub=miqp.w_max, name="w")
        y = model.addVars(N, vtype=GRB.BINARY, name="y")

        # Coupling: w_min · y_i ≤ w_i ≤ w_max · y_i.
        # Upper bound forces w_i = 0 when y_i = 0; the lower bound forces a
        # selected asset (y_i = 1) to carry at least w_min → exactly-K nonzero.
        for i in range(N):
            model.addConstr(w[i] <= miqp.w_max * y[i])
            if miqp.w_min > 0.0:
                model.addConstr(w[i] >= miqp.w_min * y[i])

        # Budget: Σ w_i = 1
        model.addConstr(gp.quicksum(w[i] for i in range(N)) == 1.0)

        # Cardinality: Σ y_i = K
        model.addConstr(gp.quicksum(y[i] for i in range(N)) == miqp.K)

        # Objective: (γ/2) wᵀΣw - μᵀw + λ_t ‖w - w_ref‖²
        risk = gp.quicksum(
            0.5 * miqp.gamma * miqp.Sigma[i, j] * w[i] * w[j] for i in range(N) for j in range(N)
        )
        ret = gp.quicksum(miqp.mu[i] * w[i] for i in range(N))
        if miqp.lambda_t > 0.0:
            turnover = gp.quicksum(
                miqp.lambda_t * (w[i] - miqp.w_ref[i]) * (w[i] - miqp.w_ref[i]) for i in range(N)
            )
        else:
            turnover = 0.0

        model.setObjective(risk - ret + turnover, GRB.MINIMIZE)

        t0 = time.perf_counter()
        model.optimize()
        elapsed = time.perf_counter() - t0

        if model.SolCount == 0:
            raise SolverFailed(f"Gurobi returned no solution (status {model.Status})")

        weights = np.array([w[i].X for i in range(N)])
        # Defer feasibility judgement to the router; we set feasible=True
        # tentatively here because Gurobi natively respects the constraints.
        return Solution(
            weights=weights,
            objective=float(model.ObjVal),
            solve_time_s=elapsed,
            provider="gurobi",
            provider_role="CPU",
            feasible=True,
            raw_bitstring=None,
        )

    def solve_qubo(self, qubo: QuboMatrix, miqp: MIQPProblem, deadline_s: float) -> Solution:
        # Gurobi races on the native MIQP — no need to go through QUBO.
        return self.solve_miqp(miqp, deadline_s)
