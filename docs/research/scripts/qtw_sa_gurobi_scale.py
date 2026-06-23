"""Answer two questions with data:
  A. Does MORE SA compute (reads AND/OR sweeps) escape the local min, or is it a true trap?
  B. How far does Gurobi scale, and WHERE does it stop proving optimality (MIP gap / time-limit)?

Yahoo universe, select encoding, β set explicitly (frac×scale) to match the §8/§9 runs. Free (no QPU).
"""

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("METHOD3_ENCODING", "select")
import yfinance as yf

from backend.financial.estimators.covariance import covariance
from backend.financial.estimators.expected_return import expected_return
from backend.financial.projection import greedy_project
from backend.financial.qubo_encoder import encode_select, select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.api.schemas import SliderValues
from backend.financial.types import PortfolioProblem, correlation_matrix
from backend.financial.weighting import optimal_weights
from backend.solvers.sampling import select_solution
from neal import SimulatedAnnealingSampler

UNIVERSE = ("AAPL MSFT GOOGL AMZN NVDA META TSLA JPM V WMT XOM JNJ PG HD KO DIS BAC CVX HON IBM AMD "
            "INTC AVGO MU QCOM ORCL CRM ADBE NFLX CSCO PEP COST MCD NKE TMO ABT ACN TXN UNH PFE MRK "
            "LLY WFC GS MS C AXP CAT BA GE MMM SPY QQQ GLD SLV TLT IONQ RGTI QBTS "
            "BTC-USD ETH-USD SOL-USD XRP-USD ADA-USD DOGE-USD AVAX-USD LINK-USD DOT-USD LTC-USD "
            "BCH-USD ATOM-USD").split()
sa = SimulatedAnnealingSampler()


def fetch():
    raw = yf.download(UNIVERSE, period="5y", interval="1d", auto_adjust=True, progress=False)["Close"]
    rets = np.clip(raw.pct_change().to_numpy()[1:], -0.5, 0.5)
    tk = list(raw.columns)
    keep = [i for i in range(len(tk)) if np.isfinite(rets[:, i]).sum() >= 500]
    return rets[:, keep], [tk[i] for i in keep]


def build(R, tickers, K, beta_frac):
    train = R[-252:]
    classes = ["crypto" if t.endswith("-USD") else "stock" for t in tickers]
    p = PortfolioProblem(
        mu=np.asarray(expected_return(train, 63), float), Sigma=np.asarray(covariance(train, classes), float),
        gamma=map_sliders(SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50,
                                       holdCount=K), len(tickers)).gamma,
        w_max=0.5, w_min=1 / 32, asset_tickers=tickers, cardinality_k=K, n_units_M=32, u_min_units=1,
    )
    p.frustration_beta = beta_frac * select_objective_scale(p) if beta_frac else 0.0
    return p


def gurobi_solve(p, time_limit):
    import gurobipy as gp
    from gurobipy import GRB
    N = p.N
    env = gp.Env(empty=True); env.setParam("OutputFlag", 0); env.start()
    m = gp.Model("pf", env=env); m.setParam("TimeLimit", time_limit)
    w = m.addVars(N, lb=0.0, ub=p.w_max); y = m.addVars(N, vtype=GRB.BINARY)
    for i in range(N):
        m.addConstr(w[i] <= p.w_max * y[i]); m.addConstr(w[i] >= p.w_min * y[i])
    m.addConstr(gp.quicksum(y[i] for i in range(N)) == p.cardinality_k)
    m.addConstr(gp.quicksum(w[i] for i in range(N)) == 1.0)
    risk = gp.quicksum(0.5 * p.gamma * p.Sigma[i, j] * w[i] * w[j] for i in range(N) for j in range(N))
    obj = risk - gp.quicksum(p.mu[i] * w[i] for i in range(N))
    if p.frustration_beta:
        rho = correlation_matrix(p.Sigma)
        obj = obj + gp.quicksum(p.frustration_beta * float(rho[i, j]) * y[i] * y[j]
                                for i in range(N) for j in range(i + 1, N))
        m.params.NonConvex = 2
    m.setObjective(obj, GRB.MINIMIZE)
    m.optimize()
    status = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT"}.get(m.Status, str(m.Status))
    return float(m.ObjVal), float(m.MIPGap), status, float(m.Runtime)


def sa_best(p, qd, qubo, reads, sweeps):
    r = sa.sample_qubo(qd, num_reads=reads, num_sweeps=sweeps, seed=0)
    best = min(p.objective(select_solution(r, qubo, p)[0]) for _ in [0])  # select_solution scans all reads
    col = {v: i for i, v in enumerate(r.variables)}
    X = r.record.sample[:, [col[i] for i in range(p.N)]]
    uniq = len({greedy_project(X[j], p) for j in range(0, len(X), max(1, len(X) // 50))})
    return best, uniq


R, tickers = fetch()
print(f"universe: {len(tickers)} names, {R.shape[0]} bars\n")

# ============ PART A — SA reads × sweeps escalation on a TRAPPED instance ============
print("== PART A: SA reads×sweeps escalation, 40a/K13 β=0.25 (a known trap) ==")
pA = build(R[:, :40], tickers[:40], 13, 0.25)
qA = encode_select(pA); qdA = qA.to_dict()
gobjA, _, _, _ = gurobi_solve(pA, 60.0)
print(f"Gurobi(60s) reference objective: {gobjA:.6f}")
print(f"{'reads':>7} {'sweeps':>7} {'gap%':>8} {'uniq/50':>8}")
for reads, sweeps in [(500, 1000), (5000, 1000), (50000, 1000), (500, 20000), (5000, 20000)]:
    b, u = sa_best(pA, qdA, qA, reads, sweeps)
    gap = 100 * (b - gobjA) / abs(gobjA)
    print(f"{reads:>7} {sweeps:>7} {gap:>8.2f} {u:>8}")

# ============ PART B — Gurobi scaling: where does it stop proving optimality? ============
print("\n== PART B: Gurobi scaling (β=0.4, 30s limit) — MIP gap + status + runtime ==")
print(f"{'N':>4} {'K':>3} {'Gur obj':>10} {'MIPgap%':>8} {'status':>11} {'runtime s':>9} {'SA gap%':>8}")
U = len(tickers)
for N in [28, 40, 60, 80, U]:
    if N > U:
        break
    K = max(3, round(N / 3))
    p = build(R[:, :N], tickers[:N], K, 0.4)
    qubo = encode_select(p)
    gobj, mipgap, status, runtime = gurobi_solve(p, 30.0)
    sab, _ = sa_best(p, qubo.to_dict(), qubo, 500, 1000)
    sa_gap = 100 * (sab - gobj) / abs(gobj) if abs(gobj) > 1e-12 else 0.0
    print(f"{N:>4} {K:>3} {gobj:>10.5f} {100 * mipgap:>8.2f} {status:>11} {runtime:>9.1f} {sa_gap:>8.2f}")
