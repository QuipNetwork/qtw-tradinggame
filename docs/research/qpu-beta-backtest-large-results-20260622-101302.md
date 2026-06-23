# β LARGE-instance OOS backtest (production greedy pipeline) — 20260622-101302

Walk-forward: train Σ720h+μ168h → hold 168h, step 168h. Selection via the production greedy projector (scales to N=24/28). β = frac×scale. Higher Sharpe = better OOS.

## 24a/K8  (windows=8, K=8, greedy pipeline)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.004 |    0.18 |    48.5 | 0/8 |
| MV β=0.25 |  0.008 |    0.32 |    41.7 | 4/8 |
| MV β=0.4  ← LIVE default |  0.009 |    0.36 |    38.8 | 5/8 |
| MV β=0.6 |  0.005 |    0.18 |    38.0 | 5/8 |
| MV β=1.0 |  0.021 |    0.66 |    31.8 | 5/8 |
| EqualWeight |  0.004 |    0.18 |    48.5 | 0/8 |

## 24a/K12  (windows=8, K=12, greedy pipeline)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.009 |    0.42 |    46.6 | 0/8 |
| MV β=0.25 |  0.012 |    0.49 |    42.4 | 5/8 |
| MV β=0.4  ← LIVE default |  0.011 |    0.44 |    41.0 | 5/8 |
| MV β=0.6 |  0.010 |    0.43 |    41.0 | 5/8 |
| MV β=1.0 |  0.009 |    0.34 |    38.3 | 4/8 |
| EqualWeight |  0.010 |    0.41 |    41.7 | 4/8 |

## 28a/K9  (windows=8, K=9, greedy pipeline)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.004 |    0.20 |    52.7 | 0/8 |
| MV β=0.25 |  0.006 |    0.28 |    48.6 | 5/8 |
| MV β=0.4  ← LIVE default |  0.001 |    0.02 |    46.5 | 5/8 |
| MV β=0.6 |  0.002 |    0.10 |    45.1 | 6/8 |
| MV β=1.0 | -0.005 |   -0.22 |    43.0 | 5/8 |
| EqualWeight |  0.001 |    0.04 |    44.1 | 5/8 |

## 28a/K14  (windows=8, K=14, greedy pipeline)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.006 |    0.26 |    39.6 | 0/8 |
| MV β=0.25 | -0.001 |   -0.03 |    34.6 | 4/8 |
| MV β=0.4  ← LIVE default |  0.005 |    0.17 |    34.2 | 4/8 |
| MV β=0.6 |  0.001 |    0.02 |    31.5 | 3/8 |
| MV β=1.0 |  0.001 |    0.02 |    30.6 | 3/8 |
| EqualWeight |  0.006 |    0.22 |    36.7 | 4/8 |

## Verdict (large instances)
Compare MV β=0.4 (live) and higher β vs β=0 on Sharpe + win-rate, and vs EqualWeight. The small backtest showed β helps mid/large baskets but hurts small — this checks whether the help grows at 24–28 assets (which would argue for a basket-size-aware β rather than a flat 0.4).

Log: /Users/azainmac/quipnetwork/qtw-tradinggame/qpu-beta-backtest-large-results-20260622-101302.md
