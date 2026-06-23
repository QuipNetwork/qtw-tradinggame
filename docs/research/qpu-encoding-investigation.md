# QPU encoding investigation — the feasibility bug, penalty-free fix, Hamming

Untracked working notes. Real data = asset-tracker.quip.network (assets-api). 2026-06-20.
Status: **penalty-free implementation PAUSED by user** — findings only, not built.

## The bug (root cause of the QPU underperforming)

`encode_method3` puts the two EQUALITY constraints into the QUBO as **dense rank-one
penalties**:
- budget  `lam_bud · outer(v, v)`, v = Gᵀ1  → couples ~every variable pair
- cardinality `lam_card · outer(s, s)`, s = 1 on all select bits → a COMPLETE graph K_N

These make the QUBO's interaction graph complete regardless of Σ → long embedding chains →
a razor-thin feasible shell → only **~2–10% of D-Wave reads land feasible**. Confirmed in
our code and in the literature (Lucas 2014 penalty bounds; D-Wave embedding/precision docs;
peer-reviewed sparse-penalty study). It is a FIXABLE encoding flaw, not a hardware limit.

## The fix (validated on real data) — PAUSED

Sample an OBJECTIVE-ONLY (penalty-free, sparse) weight QUBO; enforce Σw=1 + exactly-K in
POST-PROCESSING (top-K + renormalize). The constraints leave the QUBO entirely.

Feasibility + best-objective gap to the Gurobi optimum (500 samples each):

| basket | (A) current penalized D-Wave | (B) penalty-free D-Wave | penalty-free SA |
|---|---|---|---|
| 12a/K5 | 51/500, 11.8% | 289/500, 21.2% | 500/500, 28.7% |
| 18a/K6 | 61/500, 30.1% | 317/500, 15.6% | 500/500, 22.3% |
| 28a/K8 | 11/500, 65.1% | **426/500, 0.0%** | 500/500, 22.8% |

- Feasibility jumped **×5–40**. On 28a, penalty-free D-Wave **HIT the Gurobi optimum (0.0%)
  and BEAT SA** — the QPU shining for the first time.

## Penalty-free is SHARED by both solvers

The race hands the SAME QUBO to SA and D-Wave; the encoding choice is shared, and the
projection is identical classical post-processing. On the penalty-free PIPELINE, D-Wave
beat SA in **7/7 cells** tested (3 baskets + the 4 Hamming cells below) — D-Wave's sample
diversity surfaces better top-K selections than SA's restarts on the sparse QUBO.

## Hamming vs binary place-value (both penalty-free, both → both solvers)

Hamming (QHDOPT-style, value = #1s) is penalty-free at the VARIABLE level too (every
bitstring valid, no encoding penalty). Tested, 8 levels each:

| basket | binary place-value | hamming |
|---|---|---|
| 12a/K5 | 36v, D-Wave 258/500 @ 21.4% | 84v, D-Wave 498/500 @ 22.6% (near-100% feasible, +obj) |
| 18a/K6 | 54v, D-Wave 254/500 @ 16.4% | 126v, cb 2.3%, D-Wave 154/500 @ 18.5% (var-cost shows) |

- **Binary place-value is the better default** (better objective, scales — Hamming would be
  196v > clique cap 177 at 28a, won't embed). Hamming = small-basket-only (near-100% feasible
  but qubit-hungry). QHDOPT the library still can't express cardinality; we'd borrow only its
  Hamming encoding idea, and binary beat it anyway.

## Honest nuance — best solution per pipeline

| basket | penalized pipeline (current) | penalty-free pipeline (proposed) |
|---|---|---|
| 12a | SA ~14% ← best | D-Wave 21% |
| 18a | SA ~18% | D-Wave 16% ← best |
| 28a | SA ~23% | D-Wave 0% ← best |

Penalty-free + D-Wave wins decisively at **18+ assets**; at 12a, classical SA on the
penalized QUBO still edges it because the crude top-K+renormalize is **suboptimal
weighting**. The refinement — **optimal per-selection QP weighting** (tiny K-var QP) —
should make penalty-free dominate at all sizes. (Deferred, not yet tested.)

## QHDOPT / CQM

- **QHDOPT**: box-constrained continuous only — no integer/binary vars, no constraint API.
  Cannot express Σw=1, cardinality, or semi-continuous. Wrong tool for our problem.
- **CQM (LeapHybridCQMSampler)**: native constraints (no feasibility problem) but a 5s floor
  and the QPU does ~0.7% of the work → wrong for the live race; use OFFLINE as a quality oracle.

## SA-speedup commit dive

The recent SA speedup came from **de97dd4** (made `method3` the DEFAULT → smaller small-K
QUBO, 3N@b2 vs convex 4N@b4 → neal ~vars² faster), NOT the /code-review commit 5c0a727
(which left SA's QUBO size identical). Restore the old slower-SA / QPU-wins-on-speed
behavior via `OPTIMIZATION_MODE=convex` (env, no code change).

## Deferred for testing
1. **Optimal per-selection weighting** (vs crude renormalize) — should make penalty-free win
   at all basket sizes. Highest priority before any implementation.
2. **Robustness repeats** — D-Wave-beats-SA is 7/7 but single-run per cell; repeat 3–5×.
3. **Anneal time + dynamic num_reads** — see the section appended below.
4. **CQM offline oracle** — dev-only true-optimum reference.

## Why SA solves the "hard" cardinality problem so easily (two things conflated)

1. **Small K made SA FAST (speed, not difficulty).** method3 small-K → M=8 → b=2 → 3N QUBO
   vars (vs convex 4N at b=4). neal's per-sample cost ~ vars², so fewer vars → faster
   sampling. Pure wall-clock; says nothing about hardness.
2. **Why SA finds the OPTIMUM despite cardinality being NP-hard:**
   - NP-hard is ASYMPTOTIC / worst-case — how cost grows as N→∞, not whether a small instance
     is hard. Ours are tiny: C(12,5)=792, C(28,8)≈3M subsets; SA's 500 restarts cover them.
     A 12-variable NP-hard instance is trivially solvable.
   - The landscape is SMOOTH, not rugged (β=0): within a fixed K-subset the objective is a
     smooth convex quadratic, and the best K-set is ~"highest risk-adjusted return" — no
     deceptive local minima. The cardinality "=K" is a feasibility requirement, not deceptive
     hardness.
   - So: small SIZE + smooth LANDSCAPE → SA crushes it.
3. Cardinality added combinatorial STRUCTURE (makes the race non-trivial vs the convex single
   bowl), but structure ≠ hard at this scale. A QPU edge needs BOTH large scale AND ruggedness;
   the booth has neither by default. β injects ruggedness (SA gap grew 14%→71%) but at N≤28
   even the frustrated problem is within SA's reach, and the QPU's real bottleneck is
   feasibility (the encoding bug), not landscape.

## Anneal time + dynamic num_reads test (real data, current penalized encoding)

12a/K5 (36v), E*=-0.00067 ; 28a/K8 (84v), E*=-0.00072. Best-feasible objective gap to Gurobi.

num_reads sweep (anneal 100µs):
| reads | 12a feasible / best / qpu | 28a feasible / best / qpu |
|---|---|---|
| 100 | 7/100, 44.4%, 45ms | 2/100, 112.6%, 47ms |
| 250 | 24/250, 22.3%, 89ms | 3/250, 27.4%, 94ms |
| 500 | 75/500, 41.3%, 164ms | 14/500, 58.8%, 173ms |
| 1000 | 132/1000, 24.2%, 311ms | 20/1000, 68.2%, 330ms |

anneal sweep (num_reads 500):
| anneal | 12a feasible / best / qpu | 28a feasible / best / qpu |
|---|---|---|
| 20µs | 64, 28.7%, 124ms | 14, 63.8%, 133ms |
| 100µs | 62, 22.3%, 164ms | 15, 56.0%, 173ms |
| 300µs | 56, 31.0%, 263ms | 8, 61.1%, 273ms |
| 500µs | 50, 30.6%, 364ms | 5, 86.6%, 373ms |

**Findings:**
- **Anneal time does NOT help objective quality** — best-objective is flat/noisy across
  20–500µs (refutes the "longer anneal → better quality" hypothesis), AND longer anneal
  slightly REDUCES feasibility (64→50 at 12a, 14→5 at 28a) while costing 2–3× more QPU time.
  → 20–100µs is optimal; longer is pure waste. (Current 100µs fine; 20–50µs would be faster
  with no quality loss.)
- **num_reads: smaller = faster but feasibility scales ~linearly down** (7/100 at 12a, 2/100
  at 28a → risk of ZERO feasible). On the PENALIZED encoding you can't shrink reads much
  without losing feasibility, so there's no safe speed win there. Best-objective is a noisy
  best-of-feasible max statistic (bounces 22–44%) — needs repeats for clean trends.
- **KEY: dynamic/smaller num_reads only pays off WITH the penalty-free fix.** At ~10%
  feasibility (penalized), 100 reads → ~7 feasible (fragile). At ~60–100% feasibility
  (penalty-free), 100 reads → ~60–100 feasible → smaller reads stay consistent → D-Wave could
  run faster and compete on speed. So this lever is gated on the penalty-free encoding.


## 2026-06-20 - Web research (two-penalty encoding) + Advantage2 A/B + min-reads=500

### Research: best way to encode budget + cardinality penalties (web, cited)
Conclusion: NO published result reaches high feasibility from a dense cardinality penalty on
real D-Wave hardware. The (Σy−K)² penalty is a complete graph K_N → 83-92% chain breaks, ~0%
feasible at portfolio scale (Lozano arXiv:2605.17628 — our exact problem). Prioritized:
- P1 (best): PENALTY-FREE — keep only the easy budget penalty (Σw=1), DROP the cardinality
  penalty, enforce exactly-K by a classical top-K projector. Validated (our 11→426/500;
  Lozano same direction). Strictly better than any dense-penalty variant for raw feasibility.
- P2 (if keeping both): augmented Lagrangian — linear+quadratic term PER constraint with
  DIFFERENT weights for budget vs cardinality (QAL-BP analytic multipliers; Lucas A/B≳N bound;
  Glover 75-150%). Helps the precision/dynamic-range problem but the cardinality term is STILL
  a clique → does NOT fix embedding density/feasibility at scale.
- P3: sparse adder/sorting-network (O(N²)→O(N log N)) only pays off above ~N=40; our baskets
  ≤28 are below the crossover (ancilla overhead loses). Domain-wall is counter-productive for
  exactly-K with K≫1. LHZ/parity, perturbative gadgets: worse.
Sources incl. Lucas 1302.5843, Glover 1811.11538, Chancellor 1903.05068, sparse 2601.18108,
QAL-BP nature s41598-023-50540-3, Lozano 2605.17628.
→ Verdict: penalty-free is the answer; keeping both penalties (even optimally) can't reach high
  feasibility for cardinality at our scale.

### Advantage2 / Zephyr embedding (research + hands-on A/B, real data)
Research: Zephyr (deg 20) gives 6-21% shorter chains than Pegasus (deg 15) for cliques that
fit, but this account's Advantage2_system1 is the production ~4400q Z6 with clique cap ~105
(< Pegasus 175); no larger Zephyr announced (next roadmap = 100k multichip, not a 7k Zephyr).
Hands-on A/B (current penalized QUBO, real data):
  12a/K5 (60v): Pegasus×3 7/500 cb0.2% chain6.8 ; Zephyr×3 6/500 cb1.2% chain6.5 ; Zephyr×4 7/500
  28a/K8 (84v): Pegasus×3 3/500 cb0.4% chain8.8 ; Zephyr×3 1/500 cb12.1% chain8.5 ; Zephyr×4 0/500
→ Chains ~5% shorter on Zephyr (as predicted) but feasibility EQUAL-OR-WORSE; Zephyr×3 breaks
  spike (12% at 84v, confirming it needs ≥×4); cap 105 can't embed our 140v case. Feasibility is
  ENCODING-bound (thin feasible region from penalties), NOT topology/chain-bound. Keep Pegasus
  primary; Advantage2 doesn't help.

### Config change: D-Wave min num_reads → 500 (apples-to-apples with SA)
DWAVE_READS_BY_VARS = (48,500),(72,600),(1e9,1000). Floor now 500 = SA baseline; both solvers
draw the same minimum. 122 tests pass; tests updated.

OVERALL: research + Advantage2 both confirm feasibility is bound by the dense-penalty ENCODING,
not topology or reads. The only fix is PENALTY-FREE. Recommend implementing it next.


## 2026-06-21 - Conceptual primer: the barrier in one place (for clear learning)

WHY a QUBO forces the problem: an annealer minimizes bᵀQb over bits with NO constraints (the
"U" in QUBO). Every Method 3 constraint must be folded into the objective as a penalty (Lucas
2014). The finance objective ((γ/2)wᵀΣw − μᵀw) is benign; the two EQUALITY constraints are not.

THE MATH (why the graph goes dense):
- budget  (Σwᵢ − 1)²  = Σᵢ Σⱼ wᵢwⱼ − 2Σwᵢ + 1   → a wᵢ·wⱼ term for EVERY pair → λ·v vᵀ, v=Gᵀ1
  (rank-one but FULLY DENSE — every entry nonzero).
- card    (Σyᵢ − K)²  = 2 Σᵢ<ⱼ yᵢyⱼ + (1−2K)Σyᵢ + K²  → a yᵢ·yⱼ edge for EVERY pair of select
  bits → the COMPLETE GRAPH K_N (the "clique"). exactly-K is INTRINSICALLY all-to-all (whether
  to hold asset i depends on all the others summing to K); it cannot be written sparsely.

THE CLIQUE → why it kills the QPU (not SA):
- D-Wave is sparsely wired (Pegasus ~15 nbrs, Zephyr ~20). A complete graph must be MINOR-
  EMBEDDED: each logical var → a CHAIN of physical qubits (length ~N/4 for K_N). Long chains →
  (a) CHAIN BREAKS: chain qubits disagree under noise → corrupted reads (measured 83-92% on the
  card penalty, ~0 feasible raw); (b) PRECISION WASHOUT: ~5-bit analog range, big λ swamps the
  tiny finance coefficients → annealer can't see the good feasible point.
- SA (dwave-neal, software, float64) NEVER embeds: dense matrix = just a dense array, full
  precision sees λ AND finance at once → ~100% feasible. So the penalized encoding handicaps
  ONLY the analog QPU. That asymmetry is WHY SA wins every race on the current encoding — and
  why penalty-free (which un-handicaps the QPU) is the lever to make D-Wave competitive.

AUGMENTED LAGRANGIAN (the "linear-quadratic" option, QAL-BP): μ·g(x) + (ρ/2)·g(x)² per
constraint, separate μ,ρ for budget vs card (vs our single 12), analytic multipliers. The
linear μ-tilt lets ρ stay smaller → fixes PRECISION, but the quadratic term is STILL a clique →
does NOT fix embedding density. Best keep-the-penalty option; still can't beat the wall.

PENALTY-FREE — standard, not a patch (IF projection is done right): sample an objective-only
SPARSE QUBO; enforce exactly-K classically (top-K). Principled because cardinality is a
combinatorial SELECTION cheap to enforce classically (O(N log N)) but destructive in the QUBO —
same division-of-labor as D-Wave's own hybrid CQM. Caveat: lazy top-K+renormalize optimizes a
slightly different objective (lost to SA at 12a). FULLY principled version = QPU picks the
K-support, classical re-solves the tiny K-var QP for optimal weights on that support. (Deferred
item #1.)

VERIFIED CITATIONS (web, 2026-06-21 — IDs confirmed real, not hallucinated):
- Lucas 2014, Ising formulations of many NP problems — Frontiers in Physics; arXiv:1302.5843.
  Canonical source of the (Σ−b)² penalty method.
- Glover/Kochenberger/Du, A Tutorial on Formulating and Using QUBO Models — arXiv:1811.11538.
- QAL-BP, augmented Lagrangian for QUBO — Nature Sci. Reports 2024 s41598-023-50540-3 /
  arXiv:2309.12678. "Consistently feasible but suboptimal on medium problems due to hardware."
- arXiv:2605.17628, "A Penalty-Free Pipeline for Direct Quantum-Annealer Portfolio
  Optimization" — OUR EXACT problem + conclusion, independently: dense rank-one = all-ones
  matrix = complete graph; 83-92% chain breaks → ≤0.04% penalty-free. (Earlier "Lozano"
  attribution unverified; cite by title/ID.)
- arXiv:2605.17623, "Where the Quantum Lives in D-Wave Hybrid Portfolio Optimization" — CQM
  matches Gurobi but QPU does only 0.68% of the work → CQM = offline oracle, not live-race.
(Note: earlier-logged "Chancellor 1903.05068" and "sparse 2601.18108" NOT re-verified this
pass — treat as unconfirmed until checked.)

## 2026-06-21 - C2 vs C3 formulation + the 2026 paper (selection-only encodings)

Both encode N binary SELECTION indicators x_i in {0,1} (hold asset i or not). Equal-weight
(1/K) surrogate of subset value gives the objective over selections:
    obj(x) = - SUM mu_i x_i / K   +   (g/2K^2) SUM_ij Sigma_ij x_i x_j      [ return - risk ]

  C2 (penalty-free):  Q = objective only.   count floats -> classical greedy/top-K projects to exactly K.
  C3 (cardinality):   Q = objective + A(SUM x - K)^2.   K enforced INSIDE the QUBO.
    expand A(SUM x - K)^2 = 2A SUM_{i<j} x_i x_j + A(1-2K) SUM x_i + A K^2
    -> +A on every off-diagonal (all-ones clique) + diagonal shift. THE ONLY DIFFERENCE is this term.

Both are CLIQUES: dense covariance makes the risk term complete; C3 adds +A to the SAME edges.
Same N-node clique structure -> SAME cached clique embedding; they differ only in edge WEIGHTS.

What makes C2 combinatorial: binary subset + pairwise risk couplings -> a combinatorial (discrete-subset) problem -- but SMOOTH/easy at beta=0, NOT rugged (SA solves it; ruggedness needs the beta term -- see beta-on-C2 re-test below)
(combination effects: best 2 of {A,B(rho .9),C,D} is {A,C}, not the top-return {A,B}). The
combinatorial-ness comes from binary + interactions, NOT from the K constraint.
C2 != C3: C2 optimizes over ALL subset sizes (count set softly by the linear:quadratic ratio) then
projects; C3 optimizes over EXACTLY-K subsets. They coincide only when the risk weight is tuned so
C2's natural count = K; otherwise the optima differ. That gap is the experiment.

2026 PAPER arXiv:2605.17628 (fetched full text - formulation maps onto ours):
- variables = binary selection indicators x_i (Eq.1), NOT weight bits.
- their penalty-free QUBO  = OUR C2:   Q_obj = -diag(mu) + lambda*Sigma
- their penalty-encoded QUBO = OUR C3: Q = -diag(mu) + lambda*Sigma + A*11^T - 2AK*I
- projector = GREEDY backward/forward binary elimination; NO weight QP (they stay binary).
- budget (sum w = 1) not in their model (pure selection).
- results: penalty-encoded 83-92% chain breaks, ZERO feasible raw; penalty-free <=0.04% breaks,
  regret <=0.03% vs GREEDY classical (brute force <= N=24). NO clean same-projector
  penalty-vs-penalty-free ablation (they list the coupled study as future work).

Caveats that keep OUR C2-vs-C3 test additive (not settled by the paper):
  1. Their penalized broke 83-92% of chains; OUR x3 torque tuning gave <=2.6% breaks on penalized
     full-method3 (our failure mode was the thin feasible shell, not breaks). C3 at N<=28
     (clique chain ~3.8) + our tuning is untested by them.
  2. They stop at binary selection; WE add the convex QP weight-finish (a richer pipeline).
  3. Their bar = match greedy; OURS = gap to the Gurobi MIQP optimum (stricter).

EXPERIMENT (this session): C2 vs C3, same cached clique embedding, x3 chain, num_reads 500,
+ convex QP weight-finish, gap-to-Gurobi on real assets-api data at 12/18/28a, SA + D-Wave.
Fills the ablation the paper left open. Scoring = best-of-reads TRUE objective (g/2)wSw - mu*w
at the QP-optimal weights on each proposed support. Results appended below.

## 2026-06-21 - C2 vs C3 EXPERIMENT RESULTS (real assets-api, SA + D-Wave + Gurobi)

Setup: selection-only QUBO (N bits), equal-weight (1/K) surrogate, SAME cached Pegasus clique
embedding, x3 chain, num_reads 500, anneal 20us. Pipeline: greedy project-to-K + convex QP
weight-finish (financial.weighting.optimal_weights). Score = best-of-reads TRUE objective
(g/2)wSw - mu*w. gamma 1.5, w_max 0.5, w_min 0.02. Gurobi MIQP = oracle.
optimal_weights VALIDATED: reproduces Gurobi's objective on Gurobi's support to dev < 1e-18.

gap% = (best - gurobi)/|gurobi|.  =opt = best support == Gurobi support exactly.
| size  | method      | gap% | =opt | uniq | rawK% | time_s | cb% |
|-------|-------------|------|------|------|-------|--------|-----|
|12a/K5 | SA C2       | ~0   | deg  | 1    | 0     | 0.016  | -   |
|       | SA C3p12    | ~0   | deg  | 366  | 99.4  | 0.055  | -   |
|       | DW C2       | ~0   | deg  | 4    | 23.5  | 0.055  | 1.0 |
|       | DW C3p12    | ~0   | deg  | 315  | 59.4  | 0.055  | 0.1 |
|       | DW C3 nativeK| 0.00| yes  | 243  | -     | -      | -   |
|18a/K6 | SA C2       | 0.00 | yes  | 1    | 0     | 0.036  | -   |
|       | SA C3p12    | 2.51 | no   | 496  | 98.2  | 0.095  | -   |
|       | DW C2       | 0.00 | yes  | 9    | 13.3  | 0.056  | 4.0 |
|       | DW C3p12    | 1.52 | no   | 491  | 51.0  | 0.056  | 0.0 |
|       | DW C3 nativeK| 2.07| no   | 253  | -     | -      | -   |
|28a/K8 | SA C2       | 0.00 | yes  | 1    | 0     | 0.038  | -   |
|       | SA C3p12    | 2.02 | no   | 500  | 98.4  | 0.172  | -   |
|       | DW C2       | 0.00 | yes  | 7    | 18.3  | 0.058  | 4.1 |
|       | DW C3p12    | 1.71 | no   | 500  | 31.6  | 0.058  | 0.0 |
|       | DW C3 nativeK| 2.79| no   | 158  | -     | -      | -   |

C3 penalty-strength sweep at 28a (gap NEVER reaches 0 at any penalty; only penalty=0 i.e. C2 does):
| penalty | DW gap% | DW rawK% | DW cb% | SA gap% | SA rawK% |
|---------|---------|----------|--------|---------|----------|
| C2 (0)  | 0.00    | 14.1     | 3.7    | 0.00    | 0.0      |
| C3 p1.5 | 0.74    | 27.4     | 0.0    | 0.76    | 98.8     |
| C3 p3   | 1.42    | 31.2     | 0.0    | 0.60    | 99.2     |
| C3 p6   | 0.69    | 29.6     | 0.0    | 2.04    | 99.0     |
| C3 p12  | 1.71    | 29.6     | 0.0    | 2.02    | 98.4     |
| C3 p25  | 1.43    | 26.8     | 0.0    | 2.44    | 99.0     |
| C3 p50  | 2.08    | 25.4     | 0.1    | 1.66    | 99.0     |

CONCLUSION (decisive):
1. C2 (penalty-free + QP weight-finish) HITS the Gurobi MIQP optimum at every size on BOTH SA and
   D-Wave (gap ~0; exact support at 18a/28a). The QP weight-finish FIXES the old 12a gap (was 21%
   with renormalize -> 0% with QP). Deferred-item #1 CONFIRMED.
2. C3 (cardinality penalty) is STRICTLY WORSE at 18a/28a and at EVERY penalty strength (0.6-2.5%
   short). The optimum is reached only at penalty=0 (= C2). Adding K into the QUBO only hurts.
   (At 12a both tie - basket too small/degenerate for it to matter; the C3 gap GROWS with size.)
3. CAUSE = OBJECTIVE WASHOUT, not chain breaks: C3's chain breaks are ~0% (the uniform penalty
   even stabilizes chains) yet it still loses. The large penalty needed to enforce K dominates the
   energy -> finance objective becomes a tiny perturbation -> solver lands on feasible-but-
   suboptimal subsets (uniq scatters to 300-500). C2 makes the finance objective THE energy ->
   it concentrates on the true-best subset (uniq 1-9).
4. C3's only edge (high rawK%, native exactly-K) is irrelevant: C2's classical projector makes C2
   100% usable, and C2's projected subsets are OPTIMAL while C3's native-K subsets are 2-3% short.
5. At booth scale (<=28a) C2 makes BOTH solvers optimal; SA C2 is fastest (16-38ms). The QPU is
   feasible + optimal-quality but does NOT out-speed SA here (problem too small) - QPU edge needs scale.

DECISION: adopt C2 (penalty-free selection + greedy projector + convex QP weights). Drop C3.
Confirms AND sharpens arXiv:2605.17628: with the QP weight-finish, C2 reaches the TRUE MIQP optimum
(not just "matches greedy"); and our x3-tuned C3 isolates the failure as washout (cb ~0), not the
chain breaks the paper observed.

## 2026-06-21 - beta-on-C2 FAIR re-test: D-WAVE BEATS SA on the rugged landscape

Setup: C2 selection QUBO + beta*SUM_{i<j} rho_ij x_i x_j (frustration/diversification). EVERY read,
BOTH solvers, repaired to exactly-K (greedy) + QP weights, scored by beta-augmented p.objective()
-> best-of-500 vs best-of-500 (removes the prior beta test's feasibility confound). Gurobi-beta
MIQP = oracle. x3 chain, 20us, 500 reads. beta=frac*base, base=max|C2 coeff|. 3 repeats. Real data.

gap% to Gurobi-beta optimum (lower=better); DWwin = #repeats D-Wave strictly beats SA; uniq=distinct supports:
| size | b/base | SA gap% | DW gap% | DWwin | SA uniq | DW uniq |
|------|--------|---------|---------|-------|---------|---------|
| 12a  | all    | 0.00    | 0.00    | 0/3   | 1       | 1-23    |   (too small/degenerate to differ)
| 18a  | 0.00   | 0.00    | 0.00    | 0/3   | 1       | 4       |
| 18a  | 0.25   | 46.45   | 0.00    | 3/3   | 1       | 34      |
| 18a  | 0.50   | 113.73  | 0.00    | 3/3   | 1       | 78      |
| 18a  | 1.00   | 0.00    | 0.00    | 0/3   | 2       | 122     |   (high beta -> easy again)
| 18a  | 2.00   | 0.00    | 0.00    | 0/3   | 4       | 163     |
| 28a  | 0.00   | 0.04    | 0.00    | 3/3   | 1       | 9       |
| 28a  | 0.25   | 3.51    | 0.00    | 3/3   | 1       | 113     |
| 28a  | 0.50   | 1.20    | 0.00    | 3/3   | 2       | 194     |
| 28a  | 1.00   | 4.41    | 0.00    | 3/3   | 1       | 277     |
| 28a  | 2.00   | 4.06    | 0.00    | 3/3   | 1       | 362     |

SA UNDER-POWERING RULED OUT (SA gap INVARIANT to compute):
18a b/base=0.5: SA 113.7% at 1000sw, at 100,000sw (3.9s), AND 2000r x 20000sw (3.2s) -- uniq=1
  every config. D-Wave 0.00% in 0.056s (~70x faster, optimal).
28a b/base=1.0: SA 4.41% at every config up to 4.3s; D-Wave 0.00% in 0.058s.

FINDINGS:
1. beta=0 (smooth): tie (both ~optimal), SA faster -- as established. The QPU needs ruggedness.
2. beta>0 (rugged): D-WAVE BEATS SA ON QUALITY. 28a: D-Wave 0% at EVERY beta, SA 1.2-4.4% off,
   DWwin 3/3. 18a: DWwin 3/3 in the b/base 0.25-0.5 band (SA 46-113% off; high beta easy again).
3. SA is TRAPPED in ONE local min (uniq=1), INVARIANT to 100x sweeps / 4x reads -> a true
   deceptive-basin attractor, NOT under-powering. D-Wave's sample diversity (uniq 34-362) tunnels
   out -> global optimum, in ~1/70th of SA's max-compute time.
4. Chain breaks low (0-4.6%); oracle dev ~1e-19 (QP+beta scoring validated vs Gurobi).

SUPERSEDES the 2026-06-20 beta conclusion in tmp.txt ("QPU does not beat SA even with frustration")
-- that was CONFOUNDED by the penalized encoding's ~10% feasibility (D-Wave best-of-~60 vs SA
best-of-500). On C2 with the confound removed, D-Wave DOES beat SA on the rugged landscape.

HONEST CAVEATS:
- This is D-Wave vs SA (dwave-neal, the race's classical solver). Stronger rugged-landscape
  classical heuristics (PARALLEL TEMPERING, tabu) are UNTESTED -- they might also escape. So:
  demonstrated advantage over SA-neal (the booth's actual comparison), NOT proven vs all classical.
- beta changes the problem (adds diversification -- a legitimate portfolio goal). Advantage exists
  only where beta makes the landscape rugged; beta=0 ties.
- 18a mid-beta 113% is on a small-magnitude objective (beta nearly cancels risk-return); 28a is the
  cleaner-magnitude evidence (SA 1.2-4.4% off, unescapable). Both show the SA trap (uniq=1).

=> For the booth race (D-Wave vs SA), enabling beta (~0.25-0.5 x scale) gives D-Wave a genuine,
   robust QUALITY win -- the QPU finally shines. NEXT RIGOR FRONTIER: re-test vs parallel tempering.
