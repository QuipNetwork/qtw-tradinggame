# Overnight SA vs classical vs D-Wave — 20260622-090457

config: encode=select, chain x3.0, anneal 20us | REPS=8 | Tabu=True | D-Wave=on (cap 60) | gap% = vs Gurobi-beta optimum (lower=better)

Rigor question: on RUGGED cells, does D-Wave escape AND do SA-heavy / Tabu also escape?

## Part 1 — diverse instance grid x beta
| instance | beta | SA% | SA-heavy% | Tabu% | D-Wave% | DWwin | landscape |
|---|---|---|---|---|---|---|---|
|           12a/K4 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K4 | 0.25 |   21.01 |   21.01 |   21.01 |    0.00 |    8/8 | RUGGED |
|           12a/K4 | 0.40 |   70.61 |   70.61 |   70.61 |    0.00 |    8/8 | RUGGED |
|           12a/K4 | 0.60 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K4 | 1.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K6 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K6 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K6 | 0.40 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K6 | 0.60 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           12a/K6 | 1.00 |    1.49 |    1.49 |    1.49 |   -0.00 |    8/8 | RUGGED |
|           15a/K5 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           15a/K5 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           15a/K5 | 0.40 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           15a/K5 | 0.60 |    3.76 |    3.76 |    3.76 |   -0.00 |    8/8 | RUGGED |
|           15a/K5 | 1.00 |    7.49 |    7.49 |    7.49 |   -0.00 |    8/8 | RUGGED |
|           15a/K8 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           15a/K8 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           15a/K8 | 0.40 |    0.17 |    0.17 |    0.17 | - |      - | smooth |
|           15a/K8 | 0.60 |    1.46 |    1.46 |    1.46 |    0.00 |    8/8 | RUGGED |
|           15a/K8 | 1.00 |    8.14 |    8.14 |    8.14 |    1.43 |    8/8 | RUGGED |
|           18a/K6 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           18a/K6 | 0.25 |   13.12 |   13.12 |   13.12 |    0.00 |    4/4 | RUGGED |
|           18a/K6 | 0.40 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           18a/K6 | 0.60 |    1.57 |    1.57 |    1.57 | - |      - | RUGGED |
|           18a/K6 | 1.00 |    4.04 |    4.04 |    4.04 | - |      - | RUGGED |
|           18a/K9 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           18a/K9 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           18a/K9 | 0.40 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           18a/K9 | 0.60 |    1.75 |    1.75 |    1.75 | - |      - | RUGGED |
|           18a/K9 | 1.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           24a/K8 | 0.00 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|           24a/K8 | 0.25 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|           24a/K8 | 0.40 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|           24a/K8 | 0.60 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           24a/K8 | 1.00 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|          24a/K12 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|          24a/K12 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|          24a/K12 | 0.40 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|          24a/K12 | 0.60 |    1.58 |    1.58 |    1.58 | - |      - | RUGGED |
|          24a/K12 | 1.00 |    0.55 |    0.55 |    0.55 | - |      - | RUGGED |
|           28a/K9 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           28a/K9 | 0.25 |    7.63 |    7.63 |    7.63 | - |      - | RUGGED |
|           28a/K9 | 0.40 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|           28a/K9 | 0.60 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|           28a/K9 | 1.00 |    2.88 |    2.88 |    2.88 | - |      - | RUGGED |
|          28a/K14 | 0.00 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|          28a/K14 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|          28a/K14 | 0.40 |    1.53 |    1.53 |    1.53 | - |      - | RUGGED |
|          28a/K14 | 0.60 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|          28a/K14 | 1.00 |   -0.00 |   -0.00 |   -0.00 | - |      - | smooth |
|       15a/K5 sl8 | 0.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|       15a/K5 sl8 | 0.25 |    7.83 |    7.83 |    7.83 | - |      - | RUGGED |
|       15a/K5 sl8 | 0.40 |   56.37 |   56.37 |   56.37 | - |      - | RUGGED |
|       15a/K5 sl8 | 0.60 |  254.88 |  254.88 |  254.88 | - |      - | RUGGED |
|       15a/K5 sl8 | 1.00 |   16.42 |   16.42 |   16.42 | - |      - | RUGGED |
|       18a/K6 sl5 | 0.00 |    0.34 |    0.34 |    0.34 | - |      - | smooth |
|       18a/K6 sl5 | 0.25 |    0.00 |    0.00 |    0.00 | - |      - | smooth |
|       18a/K6 sl5 | 0.40 |    2.86 |    2.86 |    2.86 | - |      - | RUGGED |
|       18a/K6 sl5 | 0.60 |   19.65 |   19.65 |   19.65 | - |      - | RUGGED |
|       18a/K6 sl5 | 1.00 |    0.00 |    0.00 |    0.00 | - |      - | smooth |

## Part 1 summary
- cells: 60  | rugged (SA trapped >0.5%): 22
- of rugged cells: D-Wave escaped 7 | SA-heavy escaped 0 | Tabu escaped 0
- QPU calls used: 60/60

INTERPRETATION: rugged cells where D-Wave escaped but SA-heavy AND Tabu did NOT = the genuine quantum-edge regime. Cells where SA-heavy/Tabu also escaped = classical-tractable (the edge there is only vs vanilla SA).

Done. Log: /Users/azainmac/quipnetwork/qtw-tradinggame/qpu-overnight-results-20260622-090457.md
