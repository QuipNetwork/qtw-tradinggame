"""Does β help OUT-OF-SAMPLE on LARGE baskets — through the ACTUAL production pipeline?

Same walk-forward as the small backtest, but selection uses the production greedy projector
(greedy_project on the β-aware surrogate), since exact enumeration is infeasible at N=24/28. So this
tests the real shipped path at scale. Methods: MV β∈{0,0.25,0.4,0.6,1.0} (MV weights) + EqualWeight
(β0 selection, 1/K). β uses the production convention (frac × select_objective_scale). Free, no QPU.
"""

from __future__ import annotations

import datetime
import os

import numpy as np

os.environ.setdefault("METHOD3_ENCODING", "select")
ROOT = "/Users/azainmac/quipnetwork/qtw-tradinggame"

from backend import config
from backend.api.schemas import SliderValues
from backend.financial import basket
from backend.financial.estimators.covariance import covariance
from backend.financial.estimators.expected_return import expected_return
from backend.financial.prices.assets_api import AssetsApiSource
from backend.financial.prices.source import get_source, set_source
from backend.financial.projection import greedy_project
from backend.financial.qubo_encoder import select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem, correlation_matrix
from backend.financial.weighting import optimal_weights

set_source(AssetsApiSource())
ALL = list(basket.TICKERS)
BETAS = [0.0, 0.25, 0.4, 0.6, 1.0]
TRAIN_SIG, TRAIN_MU, TEST_H, STEP = config.SIGMA_WINDOW_HOURS, config.MU_WINDOW_HOURS, 168, 168
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{ROOT}/qpu-beta-backtest-large-results-{TS}.md"


def log(s=""):
    with open(LOG, "a") as f:
        f.write(s + "\n")
    print(s, flush=True)


def realized(test_R, w):
    return np.nan_to_num(test_R, nan=0.0) @ w


def stats(pool):
    a = np.asarray(pool)
    mean, vol = float(a.mean()), float(a.std())
    return mean, vol, (mean / vol if vol > 1e-12 else 0.0)


def run(label, tickers, K):
    params = map_sliders(
        SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50, holdCount=K),
        len(tickers),
    )
    gamma, w_min, w_max, k = params.gamma, params.w_min, params.w_max, params.cardinality_k
    classes = [basket.get_asset(t).asset_class for t in tickers]
    R = np.asarray(get_source().hourly_returns(tickers, 2160), dtype=float)
    T, n = R.shape
    methods = [f"MV β={b}" for b in BETAS] + ["EqualWeight"]
    pools = {m: [] for m in methods}
    cum = {m: [] for m in methods}
    windows = 0

    t = TRAIN_SIG
    while t + TEST_H <= T:
        train, test = R[t - TRAIN_SIG : t], R[t : t + TEST_H]
        mu = np.asarray(expected_return(train, TRAIN_MU), dtype=float)
        Sigma = np.asarray(covariance(train, classes), dtype=float)
        if not (np.all(np.isfinite(mu)) and np.all(np.isfinite(Sigma))):
            t += STEP
            continue
        rho = correlation_matrix(Sigma)
        zeros = np.zeros(n, dtype=np.int8)
        base_support = None
        for b in BETAS:
            p = PortfolioProblem(mu=mu, Sigma=Sigma, gamma=gamma, w_max=w_max, w_min=w_min,
                                 asset_tickers=tickers, cardinality_k=k, n_units_M=params.n_units_M,
                                 u_min_units=params.u_min_units)
            p.frustration_beta = b * select_objective_scale(p) if b else 0.0
            support = greedy_project(zeros, p, rho)  # production greedy on the β-aware surrogate
            if b == 0.0:
                base_support = support
            idx = list(support)
            w = np.zeros(n)
            w[idx] = optimal_weights(mu[idx], Sigma[np.ix_(idx, idx)], gamma, w_min, w_max)
            r = realized(test, w)
            pools[f"MV β={b}"].extend(r)
            cum[f"MV β={b}"].append(float(np.prod(1 + r) - 1))
        we = np.zeros(n)
        we[list(base_support)] = 1.0 / k
        r = realized(test, we)
        pools["EqualWeight"].extend(r)
        cum["EqualWeight"].append(float(np.prod(1 + r) - 1))
        windows += 1
        t += STEP

    log(f"## {label}  (windows={windows}, K={k}, greedy pipeline)")
    if windows == 0:
        log("(insufficient clean history)\n")
        return
    base = cum["MV β=0.0"]
    log("| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 |")
    log("|---|---|---|---|---|")
    for m in methods:
        mean, vol, sharpe = stats(pools[m])
        wb = sum(1 for i in range(windows) if cum[m][i] > base[i])
        star = "  ← LIVE default" if m == "MV β=0.4" else ""
        log(f"| {m}{star} | {sharpe:>6.3f} | {mean * 1e4:>7.2f} | {vol * 1e4:>7.1f} | {wb}/{windows} |")
    log("")


log(f"# β LARGE-instance OOS backtest (production greedy pipeline) — {TS}")
log(f"\nWalk-forward: train Σ{TRAIN_SIG}h+μ{TRAIN_MU}h → hold {TEST_H}h, step {STEP}h. Selection via the "
    "production greedy projector (scales to N=24/28). β = frac×scale. Higher Sharpe = better OOS.\n")
for label, tk, K in [("24a/K8", ALL[:24], 8), ("24a/K12", ALL[:24], 12),
                     ("28a/K9", ALL[:28], 9), ("28a/K14", ALL[:28], 14)]:
    run(label, tk, K)

log("## Verdict (large instances)")
log("Compare MV β=0.4 (live) and higher β vs β=0 on Sharpe + win-rate, and vs EqualWeight. The small "
    "backtest showed β helps mid/large baskets but hurts small — this checks whether the help grows at "
    "24–28 assets (which would argue for a basket-size-aware β rather than a flat 0.4).")
log(f"\nLog: {LOG}")
