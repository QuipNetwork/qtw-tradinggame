# β / objective out-of-sample backtest — 20260622-095338

Walk-forward: train Σ720h+μ168h → hold 168h, step 168h. Exact best-K selection (no solver noise). β = frac×scale (production convention). Higher Sharpe = better OOS.
CAVEATS: 90d history → few windows (modest power); single regime; closed-hour NaN→0; β changes SELECTION only (weights stay MV). Directional, not a multi-year backtest.

## 12a/K4  (windows=8, K=4)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 | win vs EW |
|---|---|---|---|---|---|
| MV β=0.0 | -0.007 |   -0.35 |    48.9 | 0/8 | 2/8 |
| MV β=0.25 | -0.016 |   -0.78 |    47.4 | 1/8 | 2/8 |
| MV β=0.4  ← LIVE default | -0.016 |   -0.75 |    47.0 | 2/8 | 3/8 |
| MV β=0.6 | -0.014 |   -0.63 |    45.2 | 2/8 | 3/8 |
| MV β=1.0 | -0.042 |   -1.68 |    40.3 | 2/8 | 2/8 |
| EqualWeight | -0.007 |   -0.33 |    46.0 | 6/8 | 0/8 |
| MaxDiv(μ-free) | -0.015 |   -0.41 |    27.2 | 6/8 | 6/8 |

## 15a/K5  (windows=8, K=5)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 | win vs EW |
|---|---|---|---|---|---|
| MV β=0.0 | -0.007 |   -0.37 |    55.1 | 0/8 | 3/8 |
| MV β=0.25 | -0.005 |   -0.28 |    52.7 | 4/8 | 4/8 |
| MV β=0.4  ← LIVE default | -0.007 |   -0.35 |    49.9 | 4/8 | 4/8 |
| MV β=0.6 | -0.006 |   -0.32 |    49.6 | 4/8 | 4/8 |
| MV β=1.0 | -0.010 |   -0.47 |    48.9 | 4/8 | 4/8 |
| EqualWeight | -0.001 |   -0.05 |    49.4 | 5/8 | 0/8 |
| MaxDiv(μ-free) |  0.010 |    0.43 |    44.1 | 5/8 | 5/8 |

## 18a/K6  (windows=8, K=6)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 | win vs EW |
|---|---|---|---|---|---|
| MV β=0.0 |  0.010 |    0.62 |    60.6 | 0/8 | 3/8 |
| MV β=0.25 |  0.013 |    0.76 |    58.5 | 4/8 | 5/8 |
| MV β=0.4  ← LIVE default |  0.012 |    0.69 |    57.0 | 4/8 | 5/8 |
| MV β=0.6 |  0.014 |    0.74 |    54.0 | 5/8 | 5/8 |
| MV β=1.0 |  0.016 |    0.84 |    52.8 | 4/8 | 6/8 |
| EqualWeight |  0.011 |    0.60 |    54.7 | 5/8 | 0/8 |
| MaxDiv(μ-free) |  0.008 |    0.27 |    35.7 | 5/8 | 5/8 |

## 18a/K9  (windows=8, K=9)
| method | OOS Sharpe/hr | mean ret (bps/hr) | OOS vol (bps) | win vs β0 | win vs EW |
|---|---|---|---|---|---|
| MV β=0.0 |  0.013 |    0.72 |    53.3 | 0/8 | 3/8 |
| MV β=0.25 |  0.015 |    0.78 |    52.8 | 3/8 | 4/8 |
| MV β=0.4  ← LIVE default |  0.014 |    0.73 |    52.3 | 3/8 | 5/8 |
| MV β=0.6 |  0.013 |    0.65 |    51.0 | 3/8 | 5/8 |
| MV β=1.0 |  0.017 |    0.83 |    49.8 | 4/8 | 4/8 |
| EqualWeight |  0.009 |    0.44 |    47.1 | 5/8 | 0/8 |
| MaxDiv(μ-free) |  0.006 |    0.28 |    43.4 | 6/8 | 4/8 |

## Verdict
- Compare 'MV β=0.4' (the live default) vs 'MV β=0.0' on Sharpe + win-rate: does the shipped β nudge actually help out-of-sample, or is it only buying ruggedness for the demo?
- Compare EqualWeight / MaxDiv vs MV: if naive/μ-free wins, that's the DeMiguel 1/N result and argues for shifting the objective away from μ (toward diversification) — better OOS AND rugged.

Log: /Users/azainmac/quipnetwork/qtw-tradinggame/qpu-beta-backtest-results-20260622-095338.md
