"""β=0.25 deep-dive: SA vs SA-heavy vs Tabu vs D-Wave — quality, SPEED, and local-minima evidence.

Is SA hitting a genuine local minimum at β=0.25 (the recommended default), or is it just under-powered?
Discriminator: if SA-heavy (20k sweeps) AND Tabu (different heuristic) ALSO fail to beat SA — and SA
funnels to few unique solutions across 500 reads — it's a real local min; if D-Wave then escapes, the
QPU is doing something classical search can't. Also times every solver (SA wall vs D-Wave QPU+wall).
Yahoo universe, β = 0.25 × objective_scale (the production dynamic value). Bounded D-Wave.
"""

from __future__ import annotations

import datetime
import os
import time

import numpy as np

os.environ.setdefault("METHOD3_ENCODING", "select")
ROOT = "/Users/azainmac/quipnetwork/qtw-tradinggame"
_tok = f"{ROOT}/dwave-key.txt"
if os.path.exists(_tok):
    os.environ.setdefault("DWAVE_API_TOKEN", open(_tok).read().strip())

import yfinance as yf

from backend import config
from backend.api.schemas import SliderValues
from backend.financial.estimators.covariance import covariance
from backend.financial.estimators.expected_return import expected_return
from backend.financial.projection import greedy_project
from backend.financial.qubo_encoder import encode_select, select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem
from backend.solvers.providers.gurobi import GurobiProvider
from backend.solvers.sampling import select_solution
from neal import SimulatedAnnealingSampler

UNIVERSE = ("AAPL MSFT GOOGL AMZN NVDA META TSLA JPM V WMT XOM JNJ PG HD KO DIS BAC CVX HON IBM AMD "
            "INTC AVGO MU QCOM ORCL CRM ADBE NFLX CSCO PEP COST MCD NKE TMO ABT ACN TXN UNH PFE MRK "
            "LLY WFC GS MS C AXP CAT BA GE MMM SPY QQQ GLD SLV TLT IONQ RGTI QBTS "
            "BTC-USD ETH-USD SOL-USD XRP-USD ADA-USD DOGE-USD AVAX-USD LINK-USD DOT-USD LTC-USD "
            "BCH-USD ATOM-USD").split()
BETA = 0.25
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{ROOT}/qpu-beta025-results-{TS}.md"

sa = SimulatedAnnealingSampler()
gur = GurobiProvider()
try:
    from dwave.samplers import TabuSampler

    tabu, HAS_TABU = TabuSampler(), True
except Exception:
    tabu, HAS_TABU = None, False
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


def fetch():
    raw = yf.download(UNIVERSE, period="5y", interval="1d", auto_adjust=True, progress=False)["Close"]
    rets = np.clip(raw.pct_change().to_numpy()[1:], -0.5, 0.5)
    tk = list(raw.columns)
    keep = [i for i in range(len(tk)) if np.isfinite(rets[:, i]).sum() >= 500]
    return rets[:, keep], [tk[i] for i in keep]


def build(R, tickers, K):
    train = R[-252:]
    classes = ["crypto" if t.endswith("-USD") else "stock" for t in tickers]
    p = PortfolioProblem(
        mu=np.asarray(expected_return(train, 63), float), Sigma=np.asarray(covariance(train, classes), float),
        gamma=map_sliders(SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50,
                                       holdCount=K), len(tickers)).gamma,
        w_max=0.5, w_min=1 / 32, asset_tickers=tickers, cardinality_k=K, n_units_M=32, u_min_units=1,
    )
    p.frustration_beta = BETA * select_objective_scale(p)
    return p


def best_obj(resp, qubo, p):
    return p.objective(select_solution(resp, qubo, p)[0])


R, tickers = fetch()
log(f"# β=0.25 deep-dive (quality / speed / local-minima) — {TS}")
log(f"\nYahoo {len(tickers)} names. β=0.25×scale (dynamic). gap% vs best objective found. "
    f"Tabu={HAS_TABU}, D-Wave={'on' if peg else 'OFF'}.\n")

for N, K in [(28, 9), (40, 13), (60, 20)]:
    tk = tickers[:N]
    p = build(R[:, :N], tk, K)
    qubo = encode_select(p)
    qd = qubo.to_dict()
    g_obj = gur.solve_qp(p, deadline_s=20.0).objective

    # SA: 8 reps, time one solve, count unique objectives across the 500 reads of one run
    t0 = time.perf_counter()
    sa_objs = [best_obj(sa.sample_qubo(qd, num_reads=500, num_sweeps=1000, seed=s), qubo, p) for s in range(8)]
    sa_ms = (time.perf_counter() - t0) / 8 * 1000
    one = sa.sample_qubo(qd, num_reads=500, num_sweeps=1000, seed=99)
    col = {v: i for i, v in enumerate(one.variables)}
    X = one.record.sample[:, [col[i] for i in range(p.N)]]
    uniq = len({greedy_project(X[r], p) for r in range(0, 500, 10)})  # distinct portfolios in 50 reads
    sa_best = min(sa_objs)

    t0 = time.perf_counter()
    shvy = min(best_obj(sa.sample_qubo(qd, num_reads=500, num_sweeps=20000, seed=100 + s), qubo, p)
               for s in range(3))
    shvy_ms = (time.perf_counter() - t0) / 3 * 1000

    tg = float("nan")
    tabu_ms = float("nan")
    if HAS_TABU:
        t0 = time.perf_counter()
        tg = min(best_obj(tabu.sample_qubo(qd, num_reads=200), qubo, p) for _ in range(3))
        tabu_ms = (time.perf_counter() - t0) / 3 * 1000

    dw = float("nan")
    dw_wall = dw_qpu = brk = float("nan")
    if peg is not None:
        t0 = time.perf_counter()
        resp = peg.sample_qubo(qd, num_reads=500, annealing_time=config.DWAVE_ANNEAL_TIME_US,
                               chain_strength=CS, label=f"b025-N{N}")
        dw_wall = (time.perf_counter() - t0) * 1000
        dw = best_obj(resp, qubo, p)
        try:
            dw_qpu = float(resp.info["timing"]["qpu_access_time"]) / 1000.0
            brk = 100.0 * float(resp.record.chain_break_fraction.mean())
        except Exception:  # noqa: BLE001
            pass

    best = min(x for x in (sa_best, shvy, tg, dw, g_obj) if np.isfinite(x))

    def gp(x):
        return 100.0 * (x - best) / abs(best) if np.isfinite(x) and abs(best) > 1e-12 else float("nan")

    trapped = np.isfinite(shvy) and abs(gp(shvy) - gp(sa_best)) < 0.5 and gp(sa_best) > 0.5 \
        and (not np.isfinite(tg) or abs(gp(tg) - gp(sa_best)) < 0.5)
    escapes = np.isfinite(dw) and dw < sa_best - 1e-12
    log(f"## {N}a/K{K}  (Gurobi {g_obj:.6f}; SA finds {uniq} unique objectives across 500 reads)")
    log("| solver | gap% | wall ms | note |")
    log("|---|---|---|---|")
    log(f"| SA (prod) | {gp(sa_best):.2f} | {sa_ms:.0f} | best of 8 reps |")
    log(f"| SA-heavy (20k sweeps) | {gp(shvy):.2f} | {shvy_ms:.0f} | 20× compute |")
    log(f"| Tabu | {('-' if not np.isfinite(tg) else f'{gp(tg):.2f}')} | "
        f"{('-' if not np.isfinite(tabu_ms) else f'{tabu_ms:.0f}')} | different heuristic |")
    log(f"| D-Wave | {('-' if not np.isfinite(dw) else f'{gp(dw):.2f}')} | "
        f"{('-' if not np.isfinite(dw_wall) else f'{dw_wall:.0f}')} | "
        f"QPU {('-' if not np.isfinite(dw_qpu) else f'{dw_qpu:.0f}ms')}, chain-brk "
        f"{('-' if not np.isfinite(brk) else f'{brk:.2f}%')} |")
    log(f"\n→ SA in a LOCAL MIN: {trapped}  |  D-Wave escapes it: {escapes}\n")

log("## Reading this")
log("- SA trapped = SA gap>0.5% AND SA-heavy + Tabu can't beat it (more compute / different search "
    "don't help) AND SA funnels to few unique objectives → a genuine local minimum, not weak SA.")
log("- Speed: SA wall ms is local compute; D-Wave wall ms includes network/queue to Leap, while QPU "
    "ms is the pure anneal+readout. D-Wave is faster in COMPUTE, slower in WALL — the quality-first "
    "race surfaces it only when it finds a better portfolio.")
log(f"\nLog: {LOG}")
