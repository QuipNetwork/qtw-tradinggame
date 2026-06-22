# QPU tuning results — Method 3 encoding & annealing parameters

Hardware: D-Wave Leap account, solvers below. All feasibility = cardinality-feasible
decodes (budget Σw=1 + exactly-K held + box), synthetic market, chain-strength
uniform-torque ×3 unless noted. Dates: 2026-06-19/20. Untracked working log.

## Solvers available (this account)

| solver | topology | qubits | couplers | ~degree | largest clique |
|---|---|---|---|---|---|
| Advantage_system4 | pegasus | 5627 | 40279 | 14.3 | 177 |
| Advantage_system6 | pegasus | 5612 | 40088 | 14.3 | 177 |
| Advantage2_system1 | zephyr | 4577 | 41515 | 18.1 | **105** |

Per-job QPU access is capped at **1,000,000 µs (1 s)** (~3000–3300 reads @100µs anneal).

## Variable-count scaling

Method 3 QUBO is dense (budget+Σ+cardinality+linking couple everything) → needs a
CLIQUE embedding → each logical var is a CHAIN of physical qubits. Vars = N·(1+b),
b = log2(M)−1. Measured dense-clique embeddings on Pegasus:

| logical vars | physical qubits | chain length | note |
|---|---|---|---|
| 24 | 90 | ~3.8 | |
| 84 | 740 | ~8.8 | |
| 90 | 794 | ~8.8 | |
| 140 | 1939 | ~13.8 | near Pegasus clique cap (177); chains long |

Physical ≈ O(m²), chain length ≈ O(m). The limit is CONNECTIVITY→chain length→chain
breaks, NOT qubit count (140 vars uses ~1939 of 5627 qubits, the rest unreachable
for a dense clique).

## Method 3 bit-depth × basket size (Pegasus, anneal 100µs, 500 reads)

Fewer bits = smaller M = fewer vars = more feasible (same lesson as the convex path):

| basket | b=4 (M=32, 5N) | b=3 (M=16, 4N) | b=2 (M=8, 3N) |
|---|---|---|---|
| 6 assets | 9/500 | 24/500 | 85/500 |
| 12 assets | 15/500 | 29/500 | 34/500 |
| 18 assets | 8/500 (cb 5%) | 16/500 | 10/500 |
| 28 assets | 0/500 (cb 15%) | 5/500 | 13/500 |

→ Adopted: M tied to K (`units_for_cardinality` = next pow2 ≥ max(K, 8), cap 32),
so b = log2(M)−1. Concentrated portfolios (small K) get small QUBOs → feasible.

## num_reads scaling (Pegasus, b=2)

Feasible-reads scale ~linearly (per-read rate ~constant per config):

| basket | 250 reads | 500 | 1000 | 2000 |
|---|---|---|---|---|
| 12 assets (36v) | 21 (8.4%) | 38 | 76 | 181 |
| 18 assets (54v) | 7 (2.8%) | 9 | 22 | 44 |
| 28 assets (84v) | 6 (2.4%) | 14 | 25 | 41 |

## Pegasus vs Zephyr (anneal 100µs, 500 reads)

| config | Pegasus (Advantage_system4) | Zephyr (Advantage2_system1) |
|---|---|---|
| 28a/K20/b4 (140v) | 0/500, cb 19.5% | CANNOT EMBED (cap 105) |
| 18a/K8/b4 (90v) | 7/500, cb 5.6% | 0/500, cb 9.0% |
| 28a/K6/b2 (84v) | 25/500, cb 0.6% | 0/500, cb 8.4% |

**This Zephyr is worse for our dense problems** — smaller clique (105<177) AND ~14×
the chain breaks at ×3. A full ~7000-qubit Advantage2 would likely differ, but it's
not in this account. → Pegasus is primary; pick solver EMPIRICALLY, not by degree.

## Zephyr chain-strength sweep (84v) — breaks fixable, feasibility still poor

| prefactor | feasible/500 | chain breaks |
|---|---|---|
| ×3 | 0 | 8.8% |
| ×4 | 0 | 0.2% |
| ×6 | 2 | 0.0% |
| ×8 | 4 | 0.0% |

Higher cs fixes Zephyr's breaks but feasibility stays far below Pegasus → Zephyr
needs ×4+ if ever used, but remains the worse choice here.

## Anneal time (Pegasus, 84v) — NOT a lever

| anneal | feasible/500 |
|---|---|
| 20µs | 21 |
| 100µs | 17 |
| 300µs | 15 |
| 500µs | 25 |

Flat within noise → drop to 20µs purely for speed (readout ~190µs dominates per-read).

## Spin-reversal transforms (gauge averaging) — corrected analysis

The composite returns `num_spin_reversal_transforms × num_reads` samples across
SEPARATE sub-jobs (so it ALSO bypasses the 1s/job cap). Controlling for sample count
(Pegasus, 84v, ~2000 samples each):

| run | samples | feasible | per-sample rate |
|---|---|---|---|
| srt=0, reads=500 | 500 | 22 | 4.40% |
| srt=0, reads=2000 | 2000 | 92 | 4.60% |
| srt=4, reads=500 | 2000 | 124 | **6.20%** |

→ SRT gives a genuine **~1.35× per-sample rate bonus** (bias/ICE cancellation), on
top of providing more samples via sub-jobs. The earlier raw "251/500" etc. were
mostly the k× extra samples, not a 10× rate jump. Worth enabling, size-scaled
(cost = k× QPU time, so use 0 on small/fast baskets, more on large/hard ones).

## End-to-end production path (slider→K→M→encode→size-based reads, Pegasus)

| N | K | M | vars | reads | result |
|---|---|---|---|---|---|
| 6 | 3 | 8 | 18 | 150 | feasible ✓ |
| 12 | 5 | 8 | 36 | 350 | feasible ✓ |
| 18 | 6 | 8 | 54 | 600 | feasible ✓ |
| 28 | 8 | 8 | 84 | 1000 | feasible ✓ |
| 28 | 20 | 32 | 140 | 1500 | infeasible → falls to Gurobi/SA (expected) |

Bug found + fixed here: K-dominant cap must be GRID-AWARE (`w_max ≥ ⌈M/K⌉/M`), else
the integer units can't reach the budget (N=6/K=3 was falsely infeasible).

## Conclusions / levers (in priority order)

1. **Variable count** is the primary feasibility lever → M tied to K (done).
2. **Spin-reversal transforms** — ~1.35× rate + sample-count past the 1s cap; enable
   size-scaled (small=0 for speed, large=more). Compose with reads.
3. **num_reads** — linear; size-tiered (done). With SRT adding samples, the per-job
   read ceiling can be lowered for speed.
4. **Anneal time** — flat → 20µs for speed.
5. **Solver** — Pegasus > this Zephyr for dense Method 3; select empirically; full
   Advantage2 (~7000q) worth re-checking if it appears in the account.
6. The hard 140-var (large-K diversified) case is QPU-infeasible on available
   hardware regardless → race correctly uses Gurobi/SA there.

## Implemented (adopted 2026-06-20)

- `DWAVE_ANNEAL_TIME_US` 100 → **20** (flat feasibility, free speed).
- `DWAVE_READS_BY_VARS` ceiling 1500 → **500** ((30,150),(60,350),(∞,500)) — SRT now
  supplies the extra samples, so no need for a huge single-job read count.
- `DWAVE_SRT_BY_VARS` = **(48,0),(96,2),(∞,4)** — size-scaled spin-reversal transforms
  via `SpinReversalTransformComposite` (only when srt>0; plain sampler otherwise).
- `DWAVE_SOLVER_TOPOLOGY` = **"pegasus"** — pin the better solver (overridable).

End-to-end provider confirmation (Pegasus, SRT on): 12a/K5 (36v), 18a/K6 (54v),
28a/K8 (84v), **28a/K12 (112v)** all feasible, exact held=K, Σw=1.000, 40–224ms.
The 112-var case (28-asset watchlist, hold 12) was previously marginal → now
feasible. Only the 140-var K=20 extreme stays QPU-infeasible (→ Gurobi/SA).

## CORRECTION (2026-06-20, later): SRT reverted — wall-clock regression

SRT via `SpinReversalTransformComposite` runs each gauge as a SEPARATE cloud sub-job.
The race deadline is WALL-CLOCK (router `as_completed(timeout=RACE_OVERALL_DEADLINE_S
=3.0s)`, per-solver 2.0s), and a single QPU job's wall-clock is dominated by ONE
queue+network round-trip (~1s), with QPU access only ~50–130ms. So srt=2 → 2
round-trips, srt=4 → 4 → blows the deadline. Normal instances (>48 vars, e.g. 18a/K6
=54v, 28a/K8=84v) crossed the SRT threshold and started timing out.

The timeout is JOBS, not reads. Reverted:
- `DWAVE_SRT_BY_VARS = ((1e9, 0),)` — SRT OFF in the interactive race (plumbing kept
  for offline use / if D-Wave restores single-job server-side SRT).
- `DWAVE_READS_BY_VARS` restored to size-scaled single-job tiers
  ((30,150),(48,350),(72,600),(96,1000),(1e9,1500)) — one job, cheap wall-clock,
  recovers feasibility linearly (the right lever for the race).

Confirmed on hardware (single job each, deadline 2000ms): 18a/K6 (54v) WALL=950ms,
28a/K8 (84v) WALL=1055ms, both feasible held=K. QPU access 48–133ms.

SRT remains the right tool ONLY offline (no wall-clock constraint), and only for the
90–120 var marginal band — it does NOT rescue the 140v extreme (chain-break-limited,
not bias-limited).

Total QPU access spent across all sweeps ≈ ~17 s.

---

# D-Wave solution-quality levers — full map (reference)

Everything that can move QPU solution quality, organized by where in the pipeline it
acts. Logged 2026-06-20 for understanding + a roadmap of what's tuned vs untested.

## "Sweeps" is NOT a QPU parameter

The QPU is an analog annealer — no MCMC steps. The SA↔QPU translation:

| SA (classical, dwave-neal) | QPU (quantum annealer) | meaning |
|---|---|---|
| num_reads | num_reads | independent samples |
| num_sweeps | annealing_time | how long each anneal takes |
| beta_schedule | anneal_schedule | the annealing trajectory |

So "increase sweeps" only applies to SA, not D-Wave. (And SA is already ~100%
feasible at 500/500 — see the SA section above; raising it just risks the deadline.)

## Quality is TWO axes that fight each other

```
   FEASIBILITY  — sample satisfies Σw=1, exactly-K, box   (the gate)
   OPTIMALITY   — among feasible, is the objective low?    (the prize)
```

They trade off through **coupler precision (~5%)**. To enforce constraints the penalty
terms must dominate the objective:

      E  =  E_objective  +  λ · E_penalty       (λ·penalty must dominate for feasibility)

      programmed coefficients drawn on the coupler's finite range:

      |◄──────────── λ·penalty (large) ────────────►|
                                       |◄ objective ►|   ← tiny slice
      |◄ ~5% analog noise ►|

If the objective slice is thinner than the noise band, the QPU sees "all feasible
states ≈ equal energy" → returns ANY feasible point, not the BEST. This is WHY D-Wave
reliably returns feasible-but-not-optimal. Most quality work = making the objective
survive the noise without losing feasibility.

## Levers by stage

### Stage 1 — Annealing schedule (the physics)
| lever | effect | status for us |
|---|---|---|
| annealing_time | longer ≈ more adiabatic, higher ground-state prob | TUNED — flat 20–500µs → 20µs for speed |
| pause-and-quench (anneal_schedule) | pause at the hard point s≈0.4 to thermalize, then quench to freeze it | UNTESTED — helps hard instances, costs wall-clock |
| reverse annealing | start from a classical solution, anneal backward then forward → refine a known-good answer | UNTESTED — powerful, but couples QPU to a classical seed (changes race semantics; user wants pure solvers) |
| h_gain_schedule | time-vary the biases | niche |

### Stage 2 — Embedding (logical → physical)
| lever | effect | status |
|---|---|---|
| chain_strength | bind physical qubits into one logical var | TUNED ×3 (too low→breaks; too high→squashes objective) |
| chain_break_method | majority_vote / minimize_energy / discard | UNTESTED — minimize_energy may recover more usable reads (cheap) |
| anneal_offsets | per-qubit timing; long chains freeze early — offset to sync | UNTESTED — targets large-N chain breaks; advanced |
| custom embedding | shorter chains for SPARSE QUBOs | N/A — ours is dense, clique already near-optimal |

### Stage 3 — Sampling & error mitigation
| lever | effect | status |
|---|---|---|
| num_reads | more samples → linearly more feasible | TUNED, size-scaled |
| spin-reversal transforms | cancel ICE bias (~1.35× rate) | REVERTED — composite = N cloud jobs = wall-clock; offline only |
| reduce_intersample_correlation | delay between reads → more independent samples | UNTESTED — costs time, marginal |
| programming_thermalization | settle after programming | UNTESTED — costs time, marginal |

### Stage 4 — Problem formulation (the QUBO)
| lever | effect | status |
|---|---|---|
| **penalty:objective ratio** (pmult_budget/card/link) | the central feasibility↔optimality tension | **TESTING NOW** — the real OPTIMALITY lever |
| M / bit precision | weight granularity vs variable count | TUNED (M tied to K) |
| objective dynamic-range reduction | scale/clip Σ so small couplings aren't quantized | UNTESTED — directly fights the 5%-noise problem |

### Stage 5 — Post-processing (after readout)
| lever | effect | status |
|---|---|---|
| steepest-descent polish | classical greedy local search on each readout | EXCLUDED by choice — would make QPU a hybrid; user wants QPU-alone vs SA-alone |

## Untested possibilities to revisit later (deferred)
1. **chain_break_method = minimize_energy** — cheap, may recover usable reads at large N.
2. **pause-and-quench schedule** — boost hard-instance (90–120v) success; costs wall-clock.
3. **reverse annealing from the classical seed** — strongest refiner, but hybridizes the QPU (deferred on purpose — keep solvers pure for the comparison the user wants).
4. **anneal_offsets** — sync chain freeze-out to cut chain-length-dependent breaks at 140v.
5. **objective dynamic-range reduction** (Σ scaling/clipping) — recover objective resolution within coupler precision; complements penalty-ratio tuning.
6. **reduce_intersample_correlation / programming_thermalization** — cleaner samples, costs time.
7. **steepest-descent post-processing** — excluded now (hybrid), but the cheapest pure-quality win if a hybrid path is ever acceptable.
8. **full Advantage2 (~7000q)** re-check if it appears in the account (Zephyr connectivity).

## Focus NOW: penalty:objective ratio — for OBJECTIVE QUALITY vs SA

Goal: not just fast feasibility but a feasible solution whose OBJECTIVE is competitive
with (or beats) SA — QPU-alone vs SA-alone, Gurobi MIQP as the optimum yardstick.

Hypothesis from the encoder: each penalty peak is normalized to `pmult · obj_scale`
(`encode_method3`), so pmult IS the penalty:objective ratio directly. The 2026-06-19
note found FEASIBILITY is ~flat across pmult 12–250 (QPU auto-scales). But objective
RESOLUTION should NOT be flat: higher pmult pushes the objective into the noise band
(above), so there may be a LOWER pmult that keeps feasibility while recovering
objective quality. SA is the control — full-precision arithmetic, so its objective is
penalty-insensitive once feasible; only the QPU should show the tradeoff.

### RESULTS (2026-06-20)

Synthetic data (offline) — WEAK objective signal (|E*|~0.001), so gap% is noisy and
amplified; RE-TEST ON REAL assets-api DATA. QPU-alone (Pegasus, anneal 20µs, cs×3) vs
SA-alone (500/500); Gurobi MIQP = continuous optimum; grid floor = brute-forced
integer-grid optimum (small instances). gap% = (best − optimum)/|optimum|.

Penalty sweep (best-feasible objective gap):

| instance | pmult=1 | 3 | 6 | 12 | 24 | 60 | SA (best across) |
|---|---|---|---|---|---|---|---|
| 6a/K3 (18v) | 0.0% | 5.0% | 26% | **0.0%** | 5.0% | 16% | 0% (optimum) |
| 12a/K5 (36v) | 41% | 39% | 17% | 19% | 61% | 33% | 0–13% |
| 28a/K8 (84v) | 65% | 123% | 99% | 86% | 102% | 84% | 11–40% |

Objective gap vs feasibility count (pmult=12):

| instance | reads 350 | 1000 | 2000 | SA(500) |
|---|---|---|---|---|
| 12a/K5 (36v) | 39 feas, 33.9% | 134 feas, 25.0% | 288 feas, **20.2%** | 500 feas, 14.0% |
| 28a/K8 (84v) | 0 feas, — | 1 feas, 145% | 6 feas, 93.6% | 500 feas, 22.9% |

**Findings:**
1. **pmult is NOT a clean objective lever** — no pmult reliably beats 12. Low pmult
   (1–3) loses QPU feasibility/objective; high pmult buries the objective in penalty.
   12 is a good compromise → **KEEP (no change)**. (Matches: feasibility flat in pmult.)
2. **Both SA and QPU objective degrade at high pmult** — they minimize the SAME
   penalized energy, so penalty:objective is a SHARED QUBO-quality knob, not QPU-only.
   SA's full precision keeps it ahead but doesn't immunize it (SA gap rose to ~13% at
   higher pmult on 12a).
3. **QPU objective quality is gated by FEASIBILITY COUNT** (best-of-N feasible):
   12a gap shrinks monotonically 33.9%→20.2% as feasible rises 39→288. 84v stays poor
   (too few feasible to find a good objective).
4. **QPU explores the objective** (best ≪ mean) on small instances — 6a best=−0.00104
   (= optimum) while mean=−0.00067; not just landing on random feasible points.

**Conclusion:** QPU objective is competitive with SA on small baskets (≤~36v) given
enough reads; loses on large baskets (feasibility-count-limited). pmult=12 validated
for objective too. The objective lever is feasibility COUNT, not the penalty ratio.

### THE REAL BLOCKER: the race ranks by SPEED, not objective

`router.py`: `winner = min(feasible_results, key=lambda s: s.solve_time_s)`. Objective
is recorded (`SolverRun.objective`) but NOT used to pick the winner. For D-Wave,
`solve_time_s` = QPU access time, which RISES with num_reads — so raising reads to
improve objective makes D-Wave report a SLOWER time → LESS likely to win. The lever for
"good objective" (more feasible reads) fights the current winner rule.

To actually reward good objective, the race must SCORE objective — a DESIGN decision:
- **Option A** — winner = best-objective among feasible (player gets the best portfolio;
  all solvers finished within the deadline anyway, so why pick the fastest?).
- **Option B** — keep fastest-feasible for the "quantum is fast" booth narrative, but
  surface/blend best-objective separately.

This — not a parameter — is what unlocks the user's goal ("good objective vs SA").

**DECISION (2026-06-20): Option B — keep speed winner; track objective on the BACKEND.**
Implemented (backend, kept): `SolverRun.best_objective` / `SolverResult.bestObjective`
(wire) flags the feasible solver with the lowest objective. Winner stays
`min(feasible, key=solve_time_s)` (fastest); the quality leader is computed separately.
router.py marks it; job.py + schemas.py carry it; mvp/types.ts keeps the optional wire
field (contract accuracy). Test: test_best_objective_marked_separately_from_speed_winner.

**Frontend DISPLAY: reverted per user (2026-06-20).** A kiosk/phone marker + caption
were added then removed at the user's request — the objective-quality info stays on the
backend / in the API response but is NOT shown in the UI. Re-surfacing later is a small
UI step (the data + wire field are already there).

### Deferred re-tests
- **Real assets-api data** (synthetic signal too weak for clean objective gaps).
- **Objective dynamic-range reduction** (scale/clip Σ) — recover objective resolution
  within coupler precision; complements penalty tuning. Untested.
- Stage-1/2 levers (pause schedule, chain_break_method) for the large-instance
  feasibility count that gates objective there.
