# SA vs D-Wave vs Gurobi — SELECT encoding scaling — 20260622-103432

Yahoo universe: 92 liquid names, 1826 daily bars (winsorized ±50%). One snapshot per N (Σ 252d, μ 63d). D-Wave: Pegasus clique, x3.0 chain, 20us. Gaps are vs the BEST objective found (lower=better).

| N (vars) | β | SA% | D-Wave% | Gurobi% | DW<SA? | chain-brk% | QPU ms | embed |
|---|---|---|---|---|---|---|---|---|
