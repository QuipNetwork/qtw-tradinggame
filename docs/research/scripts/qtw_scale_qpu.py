"""How big can the SELECT encoding push D-Wave? SA vs D-Wave vs Gurobi as N grows (Yahoo universe).

The select encoding is N binary vars (vs the old bit-encoding's N·b), so the D-Wave clique sampler
(~177-var max clique on Pegasus) should reach far bigger baskets than the old ~18–20 limit. This
builds ONE problem per N from a recent Yahoo window, encodes it (select), and races SA / D-Wave /
Gurobi — at β=0 (smooth → expect ties) and β=0.4 (rugged → does the QPU win at scale?). Reports each
solver's gap to the best-known objective, D-Wave chain-break % + QPU time, and where embedding fails.
Returns winsorized at ±50%/day. Bounded D-Wave (one 500-read call per cell).
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

import yfinance as yf

from backend import config
from backend.api.schemas import SliderValues
from backend.financial.estimators.covariance import covariance
from backend.financial.estimators.expected_return import expected_return
from backend.financial.qubo_encoder import encode_select, select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem
from backend.solvers.providers.gurobi import GurobiProvider
from backend.solvers.sampling import select_solution
from neal import SimulatedAnnealingSampler

STOCKS = ("AAPL MSFT GOOGL AMZN NVDA META TSLA JPM V WMT XOM JNJ PG HD KO DIS BAC CVX HON IBM AMD "
          "INTC AVGO MU QCOM ORCL CRM ADBE NFLX CSCO PEP COST MCD NKE TMO ABT ACN TXN UNH PFE MRK "
          "LLY WFC GS MS C AXP CAT BA GE MMM CVS T VZ CMCSA LOW SBUX AMAT ADI LRCX KLAC IONQ RGTI "
          "QBTS").split()
ETFS = "SPY QQQ GLD SLV TLT IWM DIA XLF XLE XLK ARKK".split()
CRYPTO = ("BTC-USD ETH-USD SOL-USD XRP-USD ADA-USD DOGE-USD AVAX-USD LINK-USD DOT-USD LTC-USD "
          "BCH-USD ATOM-USD UNI-USD XLM-USD ETC-USD FIL-USD ALGO-USD").split()
UNIVERSE = STOCKS + ETFS + CRYPTO
SIZES = [28, 40, 60, 80, 100, 120]
BETAS = [0.0, 0.4]
MIN_OBS = 500
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{ROOT}/qpu-scale-results-{TS}.md"

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


def fetch():
    raw = yf.download(UNIVERSE, period="5y", interval="1d", auto_adjust=True, progress=False)["Close"]
    rets = raw.pct_change().to_numpy()[1:]
    rets = np.clip(rets, -0.5, 0.5)  # winsorize illiquid-alt spikes
    tk = list(raw.columns)
    keep = [i for i in range(len(tk)) if np.isfinite(rets[:, i]).sum() >= MIN_OBS]
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


def obj_of(resp, qubo, p):
    w, _ = select_solution(resp, qubo, p)
    return p.objective(w)


R, tickers = fetch()
U = len(tickers)
log(f"# SA vs D-Wave vs Gurobi — SELECT encoding scaling — {TS}")
log(f"\nYahoo universe: {U} liquid names, {R.shape[0]} daily bars (winsorized ±50%). One snapshot per N "
    f"(Σ 252d, μ 63d). D-Wave: Pegasus clique, x{config.DWAVE_CHAIN_STRENGTH_PREFACTOR} chain, "
    f"{config.DWAVE_ANNEAL_TIME_US}us. Gaps are vs the BEST objective found (lower=better).\n")
log("| N (vars) | β | SA% | D-Wave% | Gurobi% | DW<SA? | chain-brk% | QPU ms | embed |")
log("|---|---|---|---|---|---|---|---|---|")

for N in SIZES:
    if N > U:
        break
    tk = tickers[:N]
    K = max(3, round(N / 3))
    for b in BETAS:
        p = build(R[:, :N], tk, K, b)
        qubo = encode_select(p)
        qd = qubo.to_dict()
        sa_obj = min(obj_of(sa.sample_qubo(qd, num_reads=500, num_sweeps=1000, seed=s), qubo, p)
                     for s in range(2))
        g = gur.solve_qp(p, deadline_s=15.0)
        g_obj = g.objective
        dw_obj = float("nan")
        brk = qpu_ms = float("nan")
        embed = "ok"
        if peg is not None:
            try:
                resp = peg.sample_qubo(qd, num_reads=500, annealing_time=config.DWAVE_ANNEAL_TIME_US,
                                       chain_strength=CS, label=f"scale-N{N}-b{b}")
                dw_obj = obj_of(resp, qubo, p)
                try:
                    brk = 100.0 * float(resp.record.chain_break_fraction.mean())
                    qpu_ms = float(resp.info["timing"]["qpu_access_time"]) / 1000.0
                except Exception:  # noqa: BLE001
                    pass
            except Exception as e:  # noqa: BLE001
                embed = f"FAIL: {str(e)[:40]}"
        best = min(x for x in (sa_obj, dw_obj, g_obj) if np.isfinite(x))

        def gap(x):
            return 100.0 * (x - best) / abs(best) if np.isfinite(x) and abs(best) > 1e-12 else float("nan")

        dwlt = "-" if not np.isfinite(dw_obj) else ("yes" if dw_obj < sa_obj - 1e-12 else "no")
        log(f"| {N}a/K{K} ({N}) | {b:>3.1f} | {gap(sa_obj):>6.2f} | "
            f"{('-' if not np.isfinite(dw_obj) else f'{gap(dw_obj):6.2f}')} | {gap(g_obj):>6.2f} | "
            f"{dwlt:>5} | {('-' if not np.isfinite(brk) else f'{brk:.2f}'):>6} | "
            f"{('-' if not np.isfinite(qpu_ms) else f'{qpu_ms:.0f}'):>6} | {embed} |")
    log("")

log("## Reading this")
log("- Select encoding = N binary vars, so D-Wave embeds far past the old N·b bit-encoding limit "
    "(~18–20 assets). 'embed' shows where the clique sampler can no longer fit the dense N-clique.")
log("- β=0 rows should be near-ties (smooth). β=0.4 rows: if 'DW<SA?'=yes and D-Wave% < SA%, the QPU "
    "is winning the rugged selection AT SCALE — the bigger-universe quantum story.")
log("- Watch chain-brk% and QPU ms grow with N; quality usually degrades before the hard embed limit.")
log(f"\nLog: {LOG}")
