# β scale-up backtest via Yahoo Finance (daily, mixed universe) — 20260622-102013

Universe: 48 names, 1826 daily bars. Train Σ90d+μ30d → hold 21d. Production greedy pipeline. β=frac×scale.
Tickers: AAPL, ADA-USD, AMD, AMZN, ARKK, ATOM-USD, AVAX-USD, AVGO, BAC, BCH-USD, BTC-USD, CVX, DIS, DOGE-USD, DOT-USD, ETH-USD, GLD, GOOGL, HD, HON, IBM, INTC, IONQ, JNJ, JPM, KO, LINK-USD, LTC-USD, META, MSFT, MU, NVDA, PG, QBTS, QCOM, QQQ, RGTI, SLV, SOL-USD, SPY, TLT, TSLA, UNI-USD, V, WMT, XLM-USD, XOM, XRP-USD

## 30a/K10  (N=30, K=10, windows=82, daily)
| method | OOS Sharpe/day | mean ret (bps/d) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.009 |    2.10 |   229.4 | 0/82 |
| MV β=0.25 |  0.009 |    1.91 |   204.7 | 47/82 |
| MV β=0.4  ← LIVE |  0.006 |    1.17 |   199.0 | 44/82 |
| MV β=0.6 |  0.005 |    0.94 |   193.7 | 43/82 |
| MV β=1.0 |  0.006 |    1.06 |   189.1 | 45/82 |
| EqualWeight |  0.022 |    3.95 |   182.5 | 51/82 |
| MaxDiv(μ-free) |  0.030 |    3.82 |   126.6 | 50/82 |

## 40a/K13  (N=40, K=13, windows=82, daily)
| method | OOS Sharpe/day | mean ret (bps/d) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.019 |    3.69 |   198.5 | 0/82 |
| MV β=0.25 |  0.028 |    4.84 |   173.8 | 45/82 |
| MV β=0.4  ← LIVE |  0.032 |    5.48 |   170.9 | 49/82 |
| MV β=0.6 |  0.027 |    4.48 |   166.7 | 46/82 |
| MV β=1.0 |  0.028 |    4.59 |   164.2 | 42/82 |
| EqualWeight |  0.023 |    3.81 |   162.4 | 47/82 |
| MaxDiv(μ-free) |  0.045 |    5.68 |   125.3 | 49/82 |

## 48a/K16  (N=48, K=16, windows=82, daily)
| method | OOS Sharpe/day | mean ret (bps/d) | OOS vol (bps) | win vs β0 |
|---|---|---|---|---|
| MV β=0.0 |  0.035 |    6.35 |   181.7 | 0/82 |
| MV β=0.25 |  0.049 |    7.86 |   160.2 | 44/82 |
| MV β=0.4  ← LIVE |  0.053 |    8.44 |   158.4 | 48/82 |
| MV β=0.6 |  0.056 |    8.91 |   157.8 | 49/82 |
| MV β=1.0 |  0.057 |    9.22 |   160.6 | 46/82 |
| EqualWeight |  0.035 |    6.35 |   181.7 | 0/82 |
| MaxDiv(μ-free) |  0.024 | 5723.62 | 236996.7 | 51/82 |

## Verdict (scale-up)
Does β still help OOS at N=30–50 (bigger than the 28-asset universe)? Compare MV β=0.4/0.25 vs β0 on Sharpe + win-rate, and MaxDiv vs the rest. More windows here → firmer signal than the 8-window runs.

Log: /Users/azainmac/quipnetwork/qtw-tradinggame/qpu-beta-backtest-yahoo-results-20260622-102013.md
