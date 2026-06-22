"""Out-of-sample backtest: does the β diversification nudge (the LIVE default, 0.4×scale) — and
alternative objectives — beat plain mean-variance on data NOT used to fit μ/Σ?

Walk-forward on real assets-api history (90d cap). At each rebalance t: TRAIN Σ(720h)+μ(168h) ending
at t, build each method's portfolio, then HOLD it fixed over the next TEST=168h and record realized
returns. Selection is EXACT best-K enumeration (no solver noise) so we measure the OBJECTIVE, not the
sampler. Closed-hour NaNs → 0 return (buy-and-hold across closed sessions).

Methods: MV β∈{0,0.25,0.4,0.6,1.0} (MV weights) · EqualWeight (β0 selection, 1/K) · MaxDiv
(min-avg-correlation selection, μ-free, 1/K). β uses the SAME convention as production
(frac × select_objective_scale). Free — no QPU.
"""

from __future__ import annotations

import datetime
import os
from itertools import combinations

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
from backend.financial.qubo_encoder import select_objective_scale
from backend.financial.slider_map import map_sliders
from backend.financial.types import PortfolioProblem, correlation_matrix
from backend.financial.weighting import optimal_weights

set_source(AssetsApiSource())
ALL = list(basket.TICKERS)
BETAS = [0.0, 0.25, 0.4, 0.6, 1.0]
TRAIN_SIG, TRAIN_MU, TEST_H, STEP = config.SIGMA_WINDOW_HOURS, config.MU_WINDOW_HOURS, 168, 168
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG = f"{ROOT}/qpu-beta-backtest-results-{TS}.md"


def log(s=""):
    with open(LOG, "a") as f:
        f.write(s + "\n")
    print(s, flush=True)


def mv_weights(support, mu, Sigma, gamma, w_min, w_max):
    idx = list(support)
    w = np.zeros(len(mu))
    w[idx] = optimal_weights(mu[idx], Sigma[np.ix_(idx, idx)], gamma, w_min, w_max)
    return w


def equal_weights(support, n):
    w = np.zeros(n)
    w[list(support)] = 1.0 / len(support)
    return w


def realized(test_R, w):
    """Per-hour portfolio returns over the test window; closed-hour NaN → 0 (held position flat)."""
    port = np.nan_to_num(test_R, nan=0.0) @ w
    return port


def stats(pool):
    a = np.asarray(pool)
    mean, vol = float(a.mean()), float(a.std())
    sharpe = mean / vol if vol > 1e-12 else 0.0
    return mean, vol, sharpe


def run(label, tickers, K):
    params = map_sliders(
        SliderValues(rebalanceFrequency=50, riskPreference=50, maxPositionSize=50, holdCount=K),
        len(tickers),
    )
    gamma, w_min, w_max, k = params.gamma, params.w_min, params.w_max, params.cardinality_k
    classes = [basket.get_asset(t).asset_class for t in tickers]
    R = np.asarray(get_source().hourly_returns(tickers, 2160), dtype=float)
    T, n = R.shape
    methods = [f"MV β={b}" for b in BETAS] + ["EqualWeight", "MaxDiv(μ-free)"]
    pools = {m: [] for m in methods}
    cum = {m: [] for m in methods}  # per-window cumulative return (for win-rate)
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
        p = PortfolioProblem(mu=mu, Sigma=Sigma, gamma=gamma, w_max=w_max, w_min=w_min,
                             asset_tickers=tickers, cardinality_k=k, n_units_M=params.n_units_M,
                             u_min_units=params.u_min_units)
        scale = select_objective_scale(p)

        # exact best-K under each objective (precompute per-subset terms once)
        coef = gamma / (2.0 * k * k)
        best = {b: (None, np.inf) for b in BETAS}
        best_div = (None, np.inf)
        for S in combinations(range(n), k):
            idx = list(S)
            sub = Sigma[np.ix_(idx, idx)]
            mv = coef * sub.sum() - mu[idx].sum() / k
            corr = 0.5 * (rho[np.ix_(idx, idx)].sum() - k)  # Σ_{i<j} ρ_ij
            for b in BETAS:
                val = mv + (b * scale) * corr
                if val < best[b][1]:
                    best[b] = (S, val)
            if corr < best_div[1]:
                best_div = (S, corr)

        for b in BETAS:
            w = mv_weights(best[b][0], mu, Sigma, gamma, w_min, w_max)
            r = realized(test, w)
            pools[f"MV β={b}"].extend(r)
            cum[f"MV β={b}"].append(float(np.prod(1 + r) - 1))
        # EqualWeight on the β=0 selection
        we = equal_weights(best[0.0][0], n)
        r = realized(test, we)
        pools["EqualWeight"].extend(r)
        cum["EqualWeight"].append(float(np.prod(1 + r) - 1))
        # MaxDiv selection (μ-free) + equal weights
        wd = equal_weights(best_div[0], n)
        r = realized(test, wd)
        pools["MaxDiv(μ-free)"].extend(r)
        cum["MaxDiv(μ-free)"].append(float(np.prod(1 + r) - 1))
        windows += 1
        t += STEP

    log(f"## {label}  (windows={windows}, K={k})")
    if windows == 0:
        log("(insufficient clean history)\n")
        return
    base_cum = cum["MV β=0.0"]
    ew_cum = cum["EqualWeight"]
    log("| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 | win vs EW |")
    log("|---|---|---|---|---|---|")
    for m in methods:
        mean, vol, sharpe = stats(pools[m])
        wb = sum(1 for i in range(windows) if cum[m][i] > base_cum[i])
        we_ = sum(1 for i in range(windows) if cum[m][i] > ew_cum[i])
        star = "  ← LIVE default" if m == "MV β=0.4" else ""
        log(f"| {m}{star} | {sharpe:>6.3f} | {mean * 1e4:>7.2f} | {vol * 1e4:>7.1f} | "
            f"{wb}/{windows} | {we_}/{windows} |")
    log("")


log(f"# β / objective out-of-sample backtest — {TS}")
log(f"\nWalk-forward: train Σ{TRAIN_SIG}h+μ{TRAIN_MU}h → hold {TEST_H}h, step {STEP}h. Exact best-K "
    f"selection (no solver noise). β = frac×scale (production convention). Higher Sharpe = better OOS.")
log("CAVEATS: 90d history → few windows (modest power); single regime; closed-hour NaN→0; β changes "
    "SELECTION only (weights stay MV). Directional, not a multi-year backtest.\n")

for label, tk, K in [("12a/K4", ALL[:12], 4), ("15a/K5", ALL[:15], 5),
                     ("18a/K6", ALL[:18], 6), ("18a/K9", ALL[:18], 9)]:
    run(label, tk, K)

log("## Verdict")
log("- Compare 'MV β=0.4' (the live default) vs 'MV β=0.0' on Sharpe + win-rate: does the shipped β "
    "nudge actually help out-of-sample, or is it only buying ruggedness for the demo?")
log("- Compare EqualWeight / MaxDiv vs MV: if naive/μ-free wins, that's the DeMiguel 1/N result and "
    "argues for shifting the objective away from μ (toward diversification) — better OOS AND rugged.")
log(f"\nLog: {LOG}")
