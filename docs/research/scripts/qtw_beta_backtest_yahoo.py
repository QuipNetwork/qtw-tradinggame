"""Scale-up β backtest on a LARGER universe via Yahoo Finance (daily bars, mixed stocks+crypto).

The assets-api universe caps at 28; this pulls ~50 liquid names from Yahoo (5y DAILY — dense for both
stocks and crypto, ~18 walk-forward windows vs the 8 we had) to test whether β helps OOS at N=30–50,
through the production greedy pipeline. Daily windows (Σ 90d, μ 30d, hold 21d). Methods: MV
β∈{0,0.25,0.4,0.6,1.0} + EqualWeight + MaxDiv(greedy, μ-free). Free, no QPU.
"""

from __future__ import annotations

import datetime
import os

import numpy as np

os.environ.setdefault("METHOD3_ENCODING", "select")
ROOT = "/Users/azainmac/quipnetwork/qtw-tradinggame"

import yfinance as yf

from backend.api.schemas import SliderValues
from backend.financial.estimators.covariance import covariance
from backend.financial.estimators.expected_return import expected_return
from backend.financial.projection import greedy_project
from backend.financial.qubo_encoder import select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem, correlation_matrix
from backend.financial.weighting import optimal_weights

UNIVERSE = [
    # mega/large-cap equity
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "WMT",
    "XOM", "JNJ", "PG", "HD", "KO", "DIS", "BAC", "CVX", "HON", "IBM",
    # semis / AI
    "AMD", "INTC", "AVGO", "MU", "QCOM",
    # quantum / themed
    "IONQ", "RGTI", "QBTS",
    # ETFs
    "SPY", "QQQ", "GLD", "SLV", "TLT", "ARKK",
    # crypto (24/7)
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD",
    "LINK-USD", "DOT-USD", "LTC-USD", "BCH-USD", "ATOM-USD", "UNI-USD", "XLM-USD",
]
BETAS = [0.0, 0.25, 0.4, 0.6, 1.0]
TRAIN_SIG, TRAIN_MU, TEST_H, STEP, MIN_OBS = 90, 30, 21, 21, 500
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{ROOT}/qpu-beta-backtest-yahoo-results-{TS}.md"


def log(s=""):
    with open(LOG, "a") as f:
        f.write(s + "\n")
    print(s, flush=True)


def fetch():
    raw = yf.download(UNIVERSE, period="5y", interval="1d", auto_adjust=True, progress=False)["Close"]
    rets = raw.pct_change().to_numpy()[1:]
    tickers = list(raw.columns)
    keep = [i for i in range(len(tickers)) if np.isfinite(rets[:, i]).sum() >= MIN_OBS]
    rets, tickers = rets[:, keep], [tickers[i] for i in keep]
    classes = ["crypto" if t.endswith("-USD") else "stock" for t in tickers]
    return rets, tickers, classes


def realized(test_R, w):
    return np.nan_to_num(test_R, nan=0.0) @ w


def stats(pool):
    a = np.asarray(pool)
    m, v = float(a.mean()), float(a.std())
    return m, v, (m / v if v > 1e-12 else 0.0)


def greedy_maxdiv(rho, k, n):
    seed = int(np.argmin(rho.sum(axis=1)))
    support = [seed]
    remaining = set(range(n)) - {seed}
    while len(support) < k:
        nxt = min(remaining, key=lambda j: sum(rho[j][s] for s in support))
        support.append(nxt)
        remaining.discard(nxt)
    return tuple(sorted(support))


def run(label, R, classes, K):
    n = R.shape[1]
    params = map_sliders(
        SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50, holdCount=K), n
    )
    gamma, w_min, w_max, k = params.gamma, params.w_min, params.w_max, params.cardinality_k
    methods = [f"MV β={b}" for b in BETAS] + ["EqualWeight", "MaxDiv(μ-free)"]
    pools = {m: [] for m in methods}
    cum = {m: [] for m in methods}
    windows = 0
    t = TRAIN_SIG
    T = R.shape[0]
    while t + TEST_H <= T:
        train, test = R[t - TRAIN_SIG : t], R[t : t + TEST_H]
        mu = np.asarray(expected_return(train, TRAIN_MU), dtype=float)
        Sigma = np.asarray(covariance(train, classes), dtype=float)
        if not (np.all(np.isfinite(mu)) and np.all(np.isfinite(Sigma))):
            t += STEP
            continue
        rho = correlation_matrix(Sigma)
        zeros = np.zeros(n, dtype=np.int8)
        base = None
        for b in BETAS:
            p = PortfolioProblem(mu=mu, Sigma=Sigma, gamma=gamma, w_max=w_max, w_min=w_min,
                                 asset_tickers=[str(i) for i in range(n)], cardinality_k=k,
                                 n_units_M=params.n_units_M, u_min_units=params.u_min_units)
            p.frustration_beta = b * select_objective_scale(p) if b else 0.0
            sup = greedy_project(zeros, p, rho)
            if b == 0.0:
                base = sup
            idx = list(sup)
            w = np.zeros(n)
            w[idx] = optimal_weights(mu[idx], Sigma[np.ix_(idx, idx)], gamma, w_min, w_max)
            r = realized(test, w)
            pools[f"MV β={b}"].extend(r)
            cum[f"MV β={b}"].append(float(np.prod(1 + r) - 1))
        for name, sup in [("EqualWeight", base), ("MaxDiv(μ-free)", greedy_maxdiv(rho, k, n))]:
            w = np.zeros(n)
            w[list(sup)] = 1.0 / k
            r = realized(test, w)
            pools[name].extend(r)
            cum[name].append(float(np.prod(1 + r) - 1))
        windows += 1
        t += STEP

    log(f"## {label}  (N={n}, K={k}, windows={windows}, daily)")
    if windows == 0:
        log("(insufficient history)\n")
        return
    b0 = cum["MV β=0.0"]
    log("| method | OOS Sharpe/day | mean ret (bps/d) | OOS vol (bps) | win vs β0 |")
    log("|---|---|---|---|---|")
    for m in methods:
        mean, vol, sh = stats(pools[m])
        wb = sum(1 for i in range(windows) if cum[m][i] > b0[i])
        star = "  ← LIVE" if m == "MV β=0.4" else ""
        log(f"| {m}{star} | {sh:>6.3f} | {mean * 1e4:>7.2f} | {vol * 1e4:>7.1f} | {wb}/{windows} |")
    log("")


log(f"# β scale-up backtest via Yahoo Finance (daily, mixed universe) — {TS}")
R, tickers, classes = fetch()
log(f"\nUniverse: {len(tickers)} names, {R.shape[0]} daily bars. Train Σ{TRAIN_SIG}d+μ{TRAIN_MU}d → "
    f"hold {TEST_H}d. Production greedy pipeline. β=frac×scale.\nTickers: {', '.join(tickers)}\n")
N = len(tickers)
for label, sub, K in [("30a/K10", R[:, :30], 10), (f"{min(40, N)}a/K13", R[:, : min(40, N)], 13),
                      (f"{N}a/K{max(5, N // 3)}", R, max(5, N // 3))]:
    cl = [classes[i] for i in range(sub.shape[1])]
    run(label, sub, cl, K)

log("## Verdict (scale-up)")
log("Does β still help OOS at N=30–50 (bigger than the 28-asset universe)? Compare MV β=0.4/0.25 vs "
    "β0 on Sharpe + win-rate, and MaxDiv vs the rest. More windows here → firmer signal than the 8-window runs.")
log(f"\nLog: {LOG}")
