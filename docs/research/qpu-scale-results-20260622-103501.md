# SA vs D-Wave vs Gurobi — SELECT encoding scaling — 20260622-103501

Yahoo universe: 92 liquid names, 1826 daily bars (winsorized ±50%). One snapshot per N (Σ 252d, μ 63d). D-Wave: Pegasus clique, x3.0 chain, 20us. Gaps are vs the BEST objective found (lower=better).

| N (vars) | β | SA% | D-Wave% | Gurobi% | DW<SA? | chain-brk% | QPU ms | embed |
|---|---|---|---|---|---|---|---|---|
| 28a/K9 (28) | 0.0 |   0.00 |   0.00 |   0.00 |    no |   2.46 |     58 | ok |
| 28a/K9 (28) | 0.4 |   4.40 |   4.40 |   0.00 |    no |   0.10 |     58 | ok |

| 40a/K13 (40) | 0.0 |   0.00 |   0.00 |   0.00 |    no |   1.39 |     61 | ok |
| 40a/K13 (40) | 0.4 |   6.24 |   2.18 |   0.00 |   yes |   0.05 |     61 | ok |

| 60a/K20 (60) | 0.0 |   0.00 |   0.00 |   0.00 |    no |   1.07 |     75 | ok |
| 60a/K20 (60) | 0.4 |   4.93 |   1.38 |   0.00 |   yes |   0.47 |     75 | ok |

| 80a/K27 (80) | 0.0 |   0.00 |   0.00 |   0.00 |    no |   0.83 |     74 | ok |
| 80a/K27 (80) | 0.4 |   3.66 |   6.53 |   0.00 |    no |   2.05 |     74 | ok |

## Reading this
- Select encoding = N binary vars, so D-Wave embeds far past the old N·b bit-encoding limit (~18–20 assets). 'embed' shows where the clique sampler can no longer fit the dense N-clique.
- β=0 rows should be near-ties (smooth). β=0.4 rows: if 'DW<SA?'=yes and D-Wave% < SA%, the QPU is winning the rugged selection AT SCALE — the bigger-universe quantum story.
- Watch chain-brk% and QPU ms grow with N; quality usually degrades before the hard embed limit.

Log: /Users/azainmac/quipnetwork/qtw-tradinggame/qpu-scale-results-20260622-103501.md
