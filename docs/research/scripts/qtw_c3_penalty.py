"""C3 (cardinality-penalty QUBO) vs C2 (penalty-free) — SA vs D-Wave, penalty-strength sweep.

C2 (production): penalty-free N-bit selection surrogate; cardinality enforced CLASSICALLY by the
greedy projector + convex QP. C3: add a HARD penalty A·(Σx − K)² so the QUBO itself drives toward
exactly-K. Expanding (Σx − K)² = (1−2K)·Σx + 2·Σ_{i<j} x_i x_j + K²:
    diagonal[i] += A·(1−2K)      pair(i,j) += 2A   (a DENSE all-pairs CLIQUE)

That clique is the same structure that handicapped the convex budget penalty on D-Wave (long
embedding chains). This sweeps A = c·objective_scale and measures, for SA and D-Wave:
  - NATIVE feasibility: fraction of the 500 reads that decode to EXACTLY K held (penalty did its job,
    no projection)
  - native objective gap to the Gurobi MIQP optimum (best feasible read)
  - D-Wave chain-break fraction
vs the C2 reference (penalty-free + greedy projection — the production path).

Expected story: low A → cardinality violated (feas≈0); high A → feas↑ but the big uniform clique
washes the objective below QPU precision (obj-gap↑); and the clique hurts D-Wave (chain breaks↑,
native-feas < SA) — i.e. the penalty re-introduces exactly what C2 removed. β=0 isolates the penalty.

Env: MAX_QPU_CALLS (30), OUT (defaults to repo root).
"""

from __future__ import annotations

import datetime
import os

import numpy as np

os.environ.setdefault("METHOD3_ENCODING", "select")
ROOT = "/Users/azainmac/quipnetwork/qtw-tradinggame"
_tok = f"{ROOT}/dwave-key.txt"
if os.path.exists(_tok):
    os.environ.setdefault("DWAVE_API_TOKEN", open(_tok).read().strip())

from backend import config
from backend.api.schemas import SliderValues
from backend.financial import basket
from backend.financial.estimators.covariance import covariance
from backend.financial.estimators.expected_return import expected_return
from backend.financial.prices.assets_api import AssetsApiSource
from backend.financial.prices.source import get_source, set_source
from backend.financial.projection import greedy_project
from backend.financial.qubo_encoder import encode_select, select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem
from backend.financial.weighting import optimal_weights
from backend.solvers.providers.gurobi import GurobiProvider
from neal import SimulatedAnnealingSampler

set_source(AssetsApiSource())
ALL = list(basket.TICKERS)
MAX_QPU = int(os.environ.get("MAX_QPU_CALLS", 30))
A_SWEEP = [0.5, 1.0, 2.0, 4.0]  # penalty strength as a multiple of the objective scale
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{os.environ.get('OUT', ROOT)}/qpu-c3-penalty-results-{TS}.md"
qpu_calls = 0

sa = SimulatedAnnealingSampler()
gur = GurobiProvider()
peg = CS = None
if os.environ.get("DWAVE_API_TOKEN"):
    from functools import partial

    from dwave.embedding.chain_strength import uniform_torque_compensation
    from dwave.system import DWaveCliqueSampler

    peg = DWaveCliqueSampler(solver=dict(topology__type="pegasus"))
    CS = partial(uniform_torque_compensation, prefactor=config.DWAVE_CHAIN_STRENGTH_PREFACTOR)


def log(s=""):
    with open(LOG, "a") as f:
        f.write(s + "\n")
    print(s, flush=True)


def build(tickers, K, beta_frac=0.0):
    p = map_sliders(
        SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50, holdCount=K),
        len(tickers),
    )
    r = get_source().hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    cl = [basket.get_asset(x).asset_class for x in tickers]
    prob = PortfolioProblem(
        mu=expected_return(r, config.MU_WINDOW_HOURS), Sigma=covariance(r, cl), gamma=p.gamma,
        w_max=p.w_max, w_min=p.w_min, asset_tickers=tickers,
        cardinality_k=p.cardinality_k, n_units_M=p.n_units_M, u_min_units=p.u_min_units,
    )
    prob.frustration_beta = beta_frac * select_objective_scale(prob) if beta_frac else 0.0
    return prob


def add_cardinality_penalty(q2: dict, n: int, k: int, A: float) -> dict:
    q3 = dict(q2)
    for i in range(n):
        q3[(i, i)] = q3.get((i, i), 0.0) + A * (1 - 2 * k)
        for j in range(i + 1, n):
            key = (i, j) if (i, j) in q3 else (j, i)
            q3[key] = q3.get(key, 0.0) + 2.0 * A
    return q3


def true_obj(support, p):
    idx = list(support)
    if not idx:
        return float("inf")
    w = np.zeros(p.N)
    w[idx] = optimal_weights(p.mu[idx], p.Sigma[np.ix_(idx, idx)], p.gamma, p.w_min, p.w_max)
    return p.objective(w)


def selection_matrix(response, n):
    col = {v: i for i, v in enumerate(response.variables)}
    return response.record.sample[:, [col[i] for i in range(n)]]


def native_stats(X, p, gobj):
    """fraction of reads with exactly-K held, and the best true-objective gap among them."""
    k = p.cardinality_k
    held = X.sum(axis=1)
    feasible_rows = X[held == k]
    feas_pct = 100.0 * len(feasible_rows) / len(X)
    best_gap = float("nan")
    if len(feasible_rows):
        supports = {tuple(np.nonzero(row)[0]) for row in feasible_rows}
        best = min(true_obj(s, p) for s in supports)
        best_gap = 100.0 * (best - gobj) / abs(gobj) if abs(gobj) > 1e-12 else 0.0
    return feas_pct, best_gap


def chain_break(response):
    try:
        return 100.0 * float(response.record.chain_break_fraction.mean())
    except Exception:  # noqa: BLE001
        return float("nan")


def projected_gap(X, p, gobj):
    """C2 production path: greedy-project every read to K, best true-objective gap."""
    supports = {greedy_project(row, p) for row in X}
    best = min(true_obj(s, p) for s in supports)
    return 100.0 * (best - gobj) / abs(gobj) if abs(gobj) > 1e-12 else 0.0


INSTANCES = [("12a/K6", ALL[:12], 6), ("18a/K6", ALL[:18], 6),
             ("18a/K9", ALL[:18], 9), ("24a/K8", ALL[:24], 8)]

log(f"# C3 (cardinality penalty) vs C2 — SA vs D-Wave — {TS}")
log(f"\nβ=0 (isolates the penalty). num_reads=500. A = c·objective_scale. D-Wave cap {MAX_QPU}.")
log("NATIVE feas% = reads decoding to exactly-K with NO projection. obj% = gap to Gurobi MIQP.\n")

for label, tk, K in INSTANCES:
    p = build(tk, K, 0.0)
    gobj = gur.solve_qp(p, deadline_s=25.0).objective
    q2 = encode_select(p).to_dict()

    # C2 reference (penalty-free + greedy projection = production path)
    sa2 = sa.sample_qubo(q2, num_reads=500, num_sweeps=1000, seed=0)
    c2_sa = projected_gap(selection_matrix(sa2, p.N), p, gobj)
    c2_dw = float("nan")
    c2_dw_brk = float("nan")
    if peg is not None and qpu_calls < MAX_QPU:
        dw2 = peg.sample_qubo(q2, num_reads=500, annealing_time=config.DWAVE_ANNEAL_TIME_US,
                              chain_strength=CS, label="c3-study-c2ref")
        qpu_calls += 1
        c2_dw = projected_gap(selection_matrix(dw2, p.N), p, gobj)
        c2_dw_brk = chain_break(dw2)

    log(f"## {label}  (Gurobi MIQP obj {gobj:.6f})")
    log(f"C2 penalty-free (projected): SA gap {c2_sa:.2f}% | D-Wave gap "
        f"{c2_dw:.2f}% | D-Wave chain-break {c2_dw_brk:.2f}%")
    log("")
    log("| A/scale | SA feas% | SA obj%(nat) | DW feas% | DW obj%(nat) | DW chain-brk% |")
    log("|---|---|---|---|---|---|")
    scale = select_objective_scale(p)
    for c in A_SWEEP:
        A = c * scale
        q3 = add_cardinality_penalty(q2, p.N, K, A)
        sa3 = sa.sample_qubo(q3, num_reads=500, num_sweeps=1000, seed=0)
        sfeas, sgap = native_stats(selection_matrix(sa3, p.N), p, gobj)
        dfeas = dgap = dbrk = float("nan")
        if peg is not None and qpu_calls < MAX_QPU:
            dw3 = peg.sample_qubo(q3, num_reads=500, annealing_time=config.DWAVE_ANNEAL_TIME_US,
                                  chain_strength=CS, label=f"c3-A{c}")
            qpu_calls += 1
            dfeas, dgap = native_stats(selection_matrix(dw3, p.N), p, gobj)
            dbrk = chain_break(dw3)
        log(f"| {c:>5.2f} | {sfeas:>6.1f} | {sgap:>10.2f} | {dfeas:>6.1f} | "
            f"{dgap:>10.2f} | {dbrk:>10.2f} |")
    log("")

log("## Reading this")
log("- C2 (penalty-free) is the production reference: cardinality is enforced classically, so the "
    "QUBO has no clique and D-Wave is competitive. feas% is N/A there (projection guarantees K).")
log("- C3 sweet spot is narrow: too-low A → feas≈0 (cardinality violated); too-high A → the big "
    "uniform clique washes the objective below precision → obj%(nat) climbs even as feas% saturates.")
log("- SA vs D-Wave on C3: compare feas% and obj%(nat). If D-Wave's feas% < SA's and chain-break% "
    "is elevated, the penalty's all-pairs clique is handicapping the QPU embedding — the exact thing "
    "C2 was designed to avoid (penalty-free → no clique → QPU competitive).")
log(f"\nQPU calls used: {qpu_calls}/{MAX_QPU}. Log: {LOG}")
