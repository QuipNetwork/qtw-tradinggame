"""Overnight SA vs strong-classical vs D-Wave sweep + ruggedness map.

Production code path: encode_qubo (select) + select_solution (greedy project + convex QP) +
problem.objective. Real assets-api data, Gurobi-beta oracle. Comparators per (instance, beta):
  - SA         neal, prod config (500 reads x 1000 sweeps), REPS reps
  - SA-heavy   neal 500 x 20000 sweeps (is it just under-powered SA? 3 reps)
  - Tabu       dwave Tabu (strong local search), if available (3 reps)
  - D-Wave     Pegasus clique, x3 chain, 20us — ONLY on rugged cells (SA gap > RUGGED_GAP)
               and capped at MAX_QPU_CALLS to protect Leap quota
  - Gurobi     exact MIQP oracle (gap reference)

Key rigor question: where SA traps, does D-Wave escape AND do the STRONG classical solvers
(SA-heavy, Tabu) also escape? If strong classical also escapes, the quantum edge is only vs
vanilla SA. Logs incrementally to a timestamped markdown.

Env: REPS (8), MAX_QPU_CALLS (80), LOOP (0 -> 1 keeps sampling random instances until Ctrl-C).
"""

from __future__ import annotations

import datetime
import os
import random
import traceback

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
from backend.financial.qubo_encoder import encode_qubo, select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem
from backend.solvers.providers.gurobi import GurobiProvider
from backend.solvers.sampling import select_solution
from neal import SimulatedAnnealingSampler

set_source(AssetsApiSource())
ALL = list(basket.TICKERS)
REPS = int(os.environ.get("REPS", 8))
MAX_QPU = int(os.environ.get("MAX_QPU_CALLS", 80))
LOOP = os.environ.get("LOOP", "0") == "1"
RUGGED_GAP = 0.5  # % SA gap above which a cell is "rugged" -> spend QPU there
BETAS = [0.0, 0.25, 0.4, 0.6, 1.0]

TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{ROOT}/qpu-overnight-results-{TS}.md"
qpu_calls = 0
agg = {"cells": 0, "rugged": 0, "dw_beats_sa": 0, "saheavy_escaped": 0, "tabu_escaped": 0}


def log(s=""):
    with open(LOG, "a") as f:
        f.write(s + "\n")
    print(s, flush=True)


sa = SimulatedAnnealingSampler()
gur = GurobiProvider()
try:
    from dwave.samplers import TabuSampler

    tabu, HAS_TABU = TabuSampler(), True
except Exception:
    tabu, HAS_TABU = None, False
peg, CS = None, None
if os.environ.get("DWAVE_API_TOKEN"):
    try:
        from functools import partial

        from dwave.embedding.chain_strength import uniform_torque_compensation
        from dwave.system import DWaveCliqueSampler

        peg = DWaveCliqueSampler(solver=dict(topology__type="pegasus"))
        CS = partial(uniform_torque_compensation, prefactor=config.DWAVE_CHAIN_STRENGTH_PREFACTOR)
    except Exception as e:  # noqa: BLE001
        log(f"(D-Wave init failed: {e})")


def build(tickers, K, beta_frac):
    params = map_sliders(
        SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50, holdCount=K),
        len(tickers),
    )
    r = get_source().hourly_returns(tickers, config.SIGMA_WINDOW_HOURS)
    cl = [basket.get_asset(x).asset_class for x in tickers]
    p = PortfolioProblem(
        mu=expected_return(r, config.MU_WINDOW_HOURS), Sigma=covariance(r, cl),
        gamma=params.gamma, w_max=params.w_max, w_min=params.w_min, asset_tickers=tickers,
        cardinality_k=params.cardinality_k, n_units_M=params.n_units_M, u_min_units=params.u_min_units,
    )
    p.frustration_beta = beta_frac * select_objective_scale(p) if beta_frac else 0.0
    return p


def _obj(resp, qubo, p):
    w, _ = select_solution(resp, qubo, p)
    return p.objective(w)


def _gap(o, gobj):
    return 100.0 * (o - gobj) / abs(gobj) if abs(gobj) > 1e-12 else 0.0


def cell(label, tickers, K, beta_frac):
    global qpu_calls
    p = build(tickers, K, beta_frac)
    qubo = encode_qubo(p)
    gobj = gur.solve_qp(p, deadline_s=25.0).objective
    sa_objs = [_obj(sa.sample_qubo(qubo.to_dict(), num_reads=500, num_sweeps=1000, seed=r), qubo, p)
               for r in range(REPS)]
    sa_best, sa_mean = min(_gap(o, gobj) for o in sa_objs), float(np.mean([_gap(o, gobj) for o in sa_objs]))
    shvy = min(_gap(_obj(sa.sample_qubo(qubo.to_dict(), num_reads=500, num_sweeps=20000, seed=100 + r), qubo, p), gobj)
               for r in range(3))
    tg = None
    if HAS_TABU:
        tg = min(_gap(_obj(tabu.sample_qubo(qubo.to_dict(), num_reads=200), qubo, p), gobj) for _ in range(3))
    rugged = sa_mean > RUGGED_GAP
    dw_best, dw_win = None, None
    if peg is not None and rugged and qpu_calls < MAX_QPU:
        dgs, wins, nd = [], 0, 0
        for _ in range(min(REPS, MAX_QPU - qpu_calls)):
            resp = peg.sample_qubo(qubo.to_dict(), num_reads=500, annealing_time=config.DWAVE_ANNEAL_TIME_US,
                                   chain_strength=CS, label="overnight")
            qpu_calls += 1
            nd += 1
            o = _obj(resp, qubo, p)
            dgs.append(_gap(o, gobj))
            if o < min(sa_objs) - 1e-12:
                wins += 1
        dw_best, dw_win = min(dgs), f"{wins}/{nd}"
    # aggregate the rigor signal
    agg["cells"] += 1
    if rugged:
        agg["rugged"] += 1
        if shvy <= RUGGED_GAP:
            agg["saheavy_escaped"] += 1
        if tg is not None and tg <= RUGGED_GAP:
            agg["tabu_escaped"] += 1
        if dw_best is not None and dw_best <= RUGGED_GAP:
            agg["dw_beats_sa"] += 1
    log(f"| {label:>16} | {beta_frac:>4.2f} | {sa_best:>7.2f} | {shvy:>7.2f} | "
        f"{('-' if tg is None else f'{tg:7.2f}')} | {('-' if dw_best is None else f'{dw_best:7.2f}')} | "
        f"{('-' if dw_win is None else dw_win):>6} | {'RUGGED' if rugged else 'smooth':>6} |")


INSTANCES = [
    ("12a/K4", ALL[:12], 4), ("12a/K6", ALL[:12], 6),
    ("15a/K5", ALL[:15], 5), ("15a/K8", ALL[:15], 8),
    ("18a/K6", ALL[:18], 6), ("18a/K9", ALL[:18], 9),
    ("24a/K8", ALL[:24], 8), ("24a/K12", ALL[:24], 12),
    ("28a/K9", ALL[:28], 9), ("28a/K14", ALL[:28], 14),
    ("15a/K5 sl8", ALL[8:23], 5), ("18a/K6 sl5", ALL[5:23], 6),
]

log(f"# Overnight SA vs classical vs D-Wave — {TS}")
log(f"\nconfig: encode={config.METHOD3_ENCODING}, chain x{config.DWAVE_CHAIN_STRENGTH_PREFACTOR}, "
    f"anneal {config.DWAVE_ANNEAL_TIME_US}us | REPS={REPS} | Tabu={HAS_TABU} | "
    f"D-Wave={'on' if peg else 'OFF'} (cap {MAX_QPU}) | gap% = vs Gurobi-beta optimum (lower=better)\n")
log("Rigor question: on RUGGED cells, does D-Wave escape AND do SA-heavy / Tabu also escape?\n")
log("## Part 1 — diverse instance grid x beta")
log("| instance | beta | SA% | SA-heavy% | Tabu% | D-Wave% | DWwin | landscape |")
log("|---|---|---|---|---|---|---|---|")
for label, tk, K in INSTANCES:
    for b in BETAS:
        try:
            cell(label, tk, K, b)
        except Exception as e:  # noqa: BLE001
            log(f"| {label} | {b} | ERROR: {e} |")
            traceback.print_exc()

log("\n## Part 1 summary")
log(f"- cells: {agg['cells']}  | rugged (SA trapped >{RUGGED_GAP}%): {agg['rugged']}")
log(f"- of rugged cells: D-Wave escaped {agg['dw_beats_sa']} | "
    f"SA-heavy escaped {agg['saheavy_escaped']} | Tabu escaped {agg['tabu_escaped']}")
log(f"- QPU calls used: {qpu_calls}/{MAX_QPU}")
log("\nINTERPRETATION: rugged cells where D-Wave escaped but SA-heavy AND Tabu did NOT = the "
    "genuine quantum-edge regime. Cells where SA-heavy/Tabu also escaped = classical-tractable "
    "(the edge there is only vs vanilla SA).")

if LOOP:
    log("\n## Part 2 — continuous random-instance loop (Ctrl-C to stop)")
    log("| instance | beta | SA% | SA-heavy% | Tabu% | D-Wave% | DWwin | landscape |")
    log("|---|---|---|---|---|---|---|---|")
    try:
        while True:
            N = random.choice([12, 15, 18, 21, 24, 28])
            start = random.randint(0, max(0, len(ALL) - N))
            tk = ALL[start:start + N]
            K = random.randint(3, max(3, N - 2))
            b = random.choice(BETAS)
            try:
                cell(f"{N}a/K{K} s{start}", tk, K, b)
            except Exception as e:  # noqa: BLE001
                log(f"| rand | ERROR: {e} |")
            if agg["cells"] % 10 == 0:
                log(f"  ...running totals: cells={agg['cells']} rugged={agg['rugged']} "
                    f"dw_escaped={agg['dw_beats_sa']} saheavy_escaped={agg['saheavy_escaped']} "
                    f"tabu_escaped={agg['tabu_escaped']} qpu={qpu_calls}/{MAX_QPU}")
    except KeyboardInterrupt:
        log(f"\nstopped. FINAL: cells={agg['cells']} rugged={agg['rugged']} "
            f"dw_escaped={agg['dw_beats_sa']} saheavy_escaped={agg['saheavy_escaped']} "
            f"tabu_escaped={agg['tabu_escaped']} qpu={qpu_calls}")

log(f"\nDone. Log: {LOG}")
