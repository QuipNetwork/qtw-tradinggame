# C3 (cardinality penalty) vs C2 — SA vs D-Wave — 20260622-093059

β=0 (isolates the penalty). num_reads=500. A = c·objective_scale. D-Wave cap 30.
NATIVE feas% = reads decoding to exactly-K with NO projection. obj% = gap to Gurobi MIQP.

## 12a/K6  (Gurobi MIQP obj -0.000024)
C2 penalty-free (projected): SA gap 0.00% | D-Wave gap 0.00% | D-Wave chain-break 3.51%

| A/scale | SA feas% | SA obj%(nat) | DW feas% | DW obj%(nat) | DW chain-brk% |
|---|---|---|---|---|---|
|  0.50 |  100.0 |       0.00 |   54.6 |       0.00 |       0.02 |
|  1.00 |  100.0 |       0.00 |   59.8 |       0.00 |       0.04 |
|  2.00 |  100.0 |       0.00 |   60.6 |       6.00 |       0.04 |
|  4.00 |  100.0 |       0.00 |   61.7 |      21.34 |       0.02 |

## 18a/K6  (Gurobi MIQP obj -0.000018)
C2 penalty-free (projected): SA gap 0.00% | D-Wave gap 0.00% | D-Wave chain-break 1.31%

| A/scale | SA feas% | SA obj%(nat) | DW feas% | DW obj%(nat) | DW chain-brk% |
|---|---|---|---|---|---|
|  0.50 |   99.4 |       0.00 |   59.6 |     171.01 |       0.00 |
|  1.00 |   99.4 |      16.21 |   53.1 |     250.76 |       0.03 |
|  2.00 |   99.4 |      56.39 |   50.6 |     174.35 |       0.03 |
|  4.00 |   98.6 |      16.21 |   49.5 |     121.82 |       0.03 |

## 18a/K9  (Gurobi MIQP obj 0.000029)
C2 penalty-free (projected): SA gap 0.00% | D-Wave gap 0.00% | D-Wave chain-break 3.80%

| A/scale | SA feas% | SA obj%(nat) | DW feas% | DW obj%(nat) | DW chain-brk% |
|---|---|---|---|---|---|
|  0.50 |  100.0 |       0.00 |   53.4 |      98.42 |       0.03 |
|  1.00 |  100.0 |       0.00 |   55.7 |     147.20 |       0.02 |
|  2.00 |  100.0 |       0.00 |   52.6 |     158.26 |       0.01 |
|  4.00 |  100.0 |      83.38 |   60.4 |     111.83 |       0.03 |

## 24a/K8  (Gurobi MIQP obj -0.000177)
C2 penalty-free (projected): SA gap -0.00% | D-Wave gap -0.00% | D-Wave chain-break 1.81%

| A/scale | SA feas% | SA obj%(nat) | DW feas% | DW obj%(nat) | DW chain-brk% |
|---|---|---|---|---|---|
|  0.50 |   99.0 |      -0.00 |   43.8 |      81.73 |       0.03 |
|  1.00 |   99.2 |       7.43 |   44.2 |      29.59 |       0.05 |
|  2.00 |   98.8 |      35.50 |   41.4 |     104.28 |       0.02 |
|  4.00 |   99.8 |      47.50 |   41.2 |      76.81 |       0.05 |

## Reading this
- C2 (penalty-free) is the production reference: cardinality is enforced classically, so the QUBO has no clique and D-Wave is competitive. feas% is N/A there (projection guarantees K).
- C3 sweet spot is narrow: too-low A → feas≈0 (cardinality violated); too-high A → the big uniform clique washes the objective below precision → obj%(nat) climbs even as feas% saturates.
- SA vs D-Wave on C3: compare feas% and obj%(nat). If D-Wave's feas% < SA's and chain-break% is elevated, the penalty's all-pairs clique is handicapping the QPU embedding — the exact thing C2 was designed to avoid (penalty-free → no clique → QPU competitive).

QPU calls used: 20/30. Log: /Users/azainmac/quipnetwork/qtw-tradinggame/qpu-c3-penalty-results-20260622-093059.md
