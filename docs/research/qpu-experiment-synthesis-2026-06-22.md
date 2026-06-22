# QPU experiment synthesis — 2026-06-22 (real assets-api data, deployment-dev code)

Raw logs: `qpu-overnight-results-20260622-090457.md`, `qpu-c3-penalty-results-20260622-093059.md`.

## 1. Overnight (C2 select encoding) — ruggedness map + rigor frontier
60 cells (12 instances × 5 β). **22 rugged** (SA gap >0.5%).

**Rigor result (the headline):** of the rugged cells where D-Wave was tested (7, before the 60-call
cap), **D-Wave escaped every one; SA-heavy (20k sweeps) and Tabu escaped ZERO.** SA-heavy and Tabu
matched vanilla SA's gap exactly on every rugged cell → the trap is not "weak SA," it's a genuinely
hard landscape that *only* the QPU escaped. This is the defensible quantum-advantage claim.

**Ruggedness map:**
- **β = 0 → smooth everywhere** (the easy / everyone-ties regime).
- Ruggedness turns on at **β ≥ 0.25**, strongest at **low K/N (~1/3) and smaller baskets (12–18)**.
- Dramatic cases (SA → D-Wave): 12a/K4 β0.40 **70.6% → 0%**; 15a/K5-sliced β0.60 **254.9%** (untested,
  cap); 18a/K6 β0.25 **13.1% → 0%**; 15a/K5 β1.0 7.5% → 0%.
- Larger baskets (24–28) are **less consistently rugged** (24a/K8 stayed smooth at every β).
- Caveat: the 60-call D-Wave cap was hit → 15 rugged cells have no D-Wave data (all 7 tested = win).

## 2. C3 (cardinality penalty) vs C2 (penalty-free) — SA vs D-Wave
C2 reference (penalty-free + greedy projection = production): **SA 0%, D-Wave 0%** — both optimal.

C3 = add `A·(Σx−K)²` (a dense all-pairs clique), sweep A = c·objective_scale, β=0:

| | SA native-feas | D-Wave native-feas | D-Wave native obj-gap | D-Wave chain-break |
|---|---|---|---|---|
| A=0.5 | 99–100% | **44–60%** | 80–171% | ~0% |
| A=4.0 | 99–100% | 41–62% | **77–250%** | ~0% |

**Refined key finding (this corrects the earlier "clique → chain-breaks" theory):** with the clique
sampler, **chain breaks are ~0% — the embedding is fine.** The penalty kills the QPU via
**coefficient dynamic range**: the large uniform `A·(Σx−K)²` coefficients swamp the small objective
below the QPU's analog precision → D-Wave satisfies cardinality but the *portfolio is garbage*
(80–250% off). float64 SA has the range to keep both penalty and objective, so SA stays ~100% feasible
and (at low A) ~0% gap. **No penalty strength A gives D-Wave a good operating point** — feas never
reaches SA's, and objective washes out as A grows.

→ This *confirms the C2 design*: enforcing cardinality classically (projection) instead of by penalty
keeps every QUBO coefficient at the objective scale → the objective stays visible to the QPU → D-Wave
is competitive (and wins on rugged β). C3 reintroduces exactly the washout C2 removed.

## 3. Booth implications
- **Quantum-advantage demo regime:** ~12–18 assets, **K ≈ N/3**, **β ≈ 0.25–0.4**. (Low K/N + β = rugged → D-Wave wins big.)
- **K = N (hold-all, the `holdCount=None` default) is degenerate** — only one valid support → no selection → guaranteed tie, QPU does nothing. Steer away.
- **β is a real diversification preference, not just a demo knob.** Cranking it to force ruggedness could ship worse portfolios. Validate its OUT-OF-SAMPLE quality before defaulting it > 0.

## 4. Recommended next steps
1. **Realized-return backtest (free, no QPU):** split the price history (train μ/Σ → portfolio → test
   realized return); compare β=0 vs β∈{0.25,0.4} out-of-sample. Decides whether a β default is honest.
2. **K guardrails** (mostly frontend): default the hold-count to ≈N/3, cap the slider at N−1, hint at
   the top of the range. Backend: default `holdCount=None` to ≈N/3 (currently N).
3. **More D-Wave coverage** for the 15 untested rugged cells (quota permitting) to fully populate the map.

## 5. β / objective OUT-OF-SAMPLE backtest (results) — `qpu-beta-backtest-results-20260622-095338.md`
Walk-forward (8 windows, 90d cap), exact best-K selection, real data. OOS Sharpe per hour:

| instance | MV β=0 | MV β=0.4 (LIVE) | MV β=1.0 | EqualWeight | MaxDiv (μ-free) | vol: β0 → MaxDiv |
|---|---|---|---|---|---|---|
| 12a/K4 | -0.007 | -0.016 (worse) | -0.042 | -0.007 | -0.015 | 48.9 → **27.2** |
| 15a/K5 | -0.007 | -0.007 (=) | -0.010 | -0.001 | **+0.010** | 55.1 → **44.1** |
| 18a/K6 | +0.010 | +0.012 (+) | +0.016 | +0.011 | +0.008 | 60.6 → **35.7** |
| 18a/K9 | +0.013 | +0.014 (+) | +0.017 | +0.009 | +0.006 | 53.3 → **43.4** |

**Findings:**
- **β=0.4 (the LIVE default) is NOT a clear OOS win.** It's a wash on Sharpe (wins ~3–4/8 windows vs β=0), HELPS mid/large baskets slightly, but is WORSE on the small 12a/K4 (forcing diversification across only 4 names sacrifices return). Its one consistent effect is **lower volatility**. So it's defensible as a vol/diversification preference, but it is not shipping "better portfolios" universally — and cranking β higher costs return on small baskets.
- **MaxDiv (μ-free min-correlation selection) is the standout** — **25–45% lower OOS volatility everywhere**, competitive-to-best Sharpe (best on 15a/K5), wins 5–6/8 vs MV-β0, AND it's μ-free (no estimation error) and the most rugged (max-dispersion = QPU-native). This empirically answers "is there a more-rugged, better-OOS objective?" → **yes, diversification-driven / μ-free selection.**
- **MV weights look over-fit:** EqualWeight (equal-weighting the same β0 selection) beats MV-weighted β0 in 5–6/8 windows → the μ-driven weight optimization adds estimation noise OOS (classic DeMiguel). Worth considering shrinkage / equal weights.
- CAVEAT: 8 windows, single near-zero-return regime → Sharpes are tiny/noisy; the **volatility reductions are the robust signal**, Sharpe deltas are directional.

**Decisions this surfaces:**
1. The live **β=0.4 default is marginal** — keep (mild vol benefit), lower to ~0.25, or make basket-size-aware (it hurts small baskets). NOT a "better portfolio" default as-is.
2. **MaxDiv is worth prototyping** as an objective/mode — rugged (QPU-native) AND robust (low vol, μ-free).
3. **Weights:** test shrinkage/equal-weighting vs the current MV `optimal_weights`.

## 6. β LARGE-instance backtest (24–28 assets, production greedy pipeline) + RECOMMENDATION
OOS Sharpe/hr (8 windows each), via the SHIPPED greedy projector + MV weights:

| instance | β0 | β0.25 | β0.4 (LIVE) | β0.6 | β1.0 | vol β0→β1.0 |
|---|---|---|---|---|---|---|
| 24a/K8  | 0.004 | 0.008 | 0.009 | 0.005 | 0.021 | 48.5→31.8 |
| 24a/K12 | 0.009 | **0.012** | 0.011 | 0.010 | 0.009 | 46.6→38.3 |
| 28a/K9  | 0.004 | **0.006** | 0.001 | 0.002 | -0.005 | 52.7→43.0 |
| 28a/K14 | 0.006 | -0.001 | 0.005 | 0.001 | 0.001 | 39.6→30.6 |

**Consolidated β finding (small + large, 8 instances):**
- **Volatility reduction is universal + monotonic in β** — the one robust, consistent effect. β is a reliable diversification/vol dial.
- **Sharpe is mixed/noisy:** β=0.25 is the most consistently good point (best-or-near-best in most instances); β=0.4 (live) is neutral (helps some, HURTS 12a/K4, 28a/K9, 28a/K14); β≥0.6 is a coin-flip and tends to cost return.
- → β is NOT a reliable Sharpe-improver; it is a volatility/diversification preference.

**RECOMMENDATION: lower the live default `CARDINALITY_FRUSTRATION_BETA` 0.4 → 0.25.** Same vol benefit,
less return sacrifice, equal-or-better Sharpe across small+large, gentler on small baskets where 0.4
hurts. Don't exceed ~0.25–0.3. Treat β as a diversification/vol dial, not a Sharpe lever. (Alt:
basket-size-aware β — ~0 for N≤12, ~0.25–0.3 for N≥15 — but flat 0.25 is simpler.)

## 7. Scale-up via Yahoo Finance (daily, 48-asset mixed universe, 82 windows — firm power)
OOS Sharpe/day, production greedy pipeline:

| N/K | β0 | β0.25 | β0.4 (LIVE) | β0.6 | β1.0 | EqualWeight | MaxDiv |
|---|---|---|---|---|---|---|---|
| 30a/K10 | 0.009 | 0.009 | 0.006 | 0.005 | 0.006 | 0.022 | **0.030** |
| 40a/K13 | 0.019 | 0.028 | 0.032 | 0.027 | 0.028 | 0.023 | **0.045** |
| 48a/K16 | 0.035 | 0.049 | 0.053 | 0.056 | **0.057** | 0.035† | (outlier‡) |

† at K=16 the w_max grid floor (1/16) forces equal weights → EqualWeight ≡ MV.
‡ MaxDiv 48a blew up on a Yahoo data outlier (illiquid-alt spike) — needs return winsorization.

**KEY NEW FINDING — β's OOS benefit SCALES WITH UNIVERSE SIZE:**
- 30 assets: β marginal/hurts (matches the 12–28 result).
- 40 assets: β helps (β0.4 0.032 vs β0 0.019).
- 48 assets: β helps clearly + monotonically (β0.4 0.053, β1.0 0.057 vs β0 0.035).
→ At the **28-asset cap β is in the marginal zone**; a **bigger universe (40–50) is where diversification
(β) genuinely pays** — and where the QPU's selection problem is largest/hardest.
- MaxDiv remains the best clean objective (30a 0.030, 40a 0.045: top Sharpe + lowest vol).

**IMPLICATIONS:**
- β default is **universe-size-dependent**: 28-asset booth → ~0.25 (or basket-aware); 40–50 → 0.4+ justified.
- **STRATEGIC:** expanding the universe (Yahoo) makes both β/diversification AND the quantum selection
  genuinely more valuable — the select encoding is N binary vars, so 48 assets = 48 vars, well within
  the D-Wave clique sampler (~180), which the old bit-encoding could never reach. Scale helps the QPU story.
- DATA HYGIENE: winsorize Yahoo returns before trusting tails (the 48a MaxDiv blowup).

## 8. SA vs D-Wave vs Gurobi — SELECT-encoding SCALING (Yahoo, up to 80 assets)
Select encoding = N binary vars, so D-Wave embeds far past the old bit-encoding's ~18–20 limit. Gaps
vs best-of-three objective (one snapshot per N, Σ252d/μ63d, winsorized):

| N | β=0 (all) | β=0.4 SA | β=0.4 D-Wave | DW<SA? | chain-brk | QPU ms | embed |
|---|---|---|---|---|---|---|---|
| 28 | 0/0/0 tie | 4.40 | 4.40 | no | 0.1% | 58 | ok |
| 40 | 0/0/0 tie | 6.24 | **2.18** | **YES** | 0.05% | 61 | ok |
| 60 | 0/0/0 tie | 4.93 | **1.38** | **YES** | 0.47% | 75 | ok |
| 80 | 0/0/0 tie | 3.66 | 6.53 | no (degraded) | 2.05% | 74 | ok |

**FINDINGS:**
- **D-Wave embeds + is optimal (β=0) all the way to 80 assets** (chain-breaks ≤2.5%, QPU ~60–75 ms).
  The select encoding gives **~4× the old QPU reach** (~18–20 → 80+).
- **D-Wave WINS the rugged (β=0.4) selection at 40 and 60 assets** — beats SA by 3–4%. The
  bigger-universe quantum story, made concrete.
- Edge **degrades by 80** (D-Wave 6.53% > SA 3.66%, chain-breaks rising) — the dense N-clique starts
  hurting. **Practical sweet spot: ~40–60 assets, β=0.4.**
- β=0 smooth/tie everywhere (no ruggedness without β).
- Universe capped at 92 liquid Yahoo names → max N=80 tested; the hard embed ceiling (~120–177 on
  Pegasus) is untested (would need a bigger universe).

**THIS CLOSES THE LOOP with §7:** at 40–60 assets, β both improves OOS (§7) AND lets D-Wave beat SA
on the selection (§8). The bigger-universe direction is validated on BOTH axes — better portfolios
*and* a genuine quantum advantage. The booth's 28-asset universe sits just below this sweet spot.

## 9. β=0.25 deep-dive — SA local minima + speed (Yahoo, 28/40/60 assets)
At the RECOMMENDED β=0.25 (dynamic, ×objective_scale), gap% vs best:

| N | SA | SA-heavy 20× | Tabu | D-Wave | SA unique sols | SA wall | D-Wave QPU |
|---|---|---|---|---|---|---|---|
| 28a/K9 | 5.60 | 5.60 | 5.60 | **2.05** | 1 / 50 reads | 221 ms | 58 ms |
| 40a/K13 | 3.49 | 3.49 | 3.49 | **1.22** | 1 / 50 reads | 551 ms | 61 ms |
| 60a/K20 | 2.58 | 2.58 | 2.58 | **0.94** | 1 / 50 reads | 2033 ms | 75 ms |

**PROVEN — SA hits a GENUINE local minimum at β=0.25 (every size):**
- SA, SA-heavy (20× sweeps), AND Tabu (different heuristic) converge to the **identical** gap → more
  compute and a different search both get nowhere.
- SA funnels **all reads into 1 unique portfolio** → one dominant attractor basin.
- **D-Wave escapes it every time** (2.05/1.22/0.94 vs 5.60/3.49/2.58) — tunnels out of the basin that
  traps every classical method. Cleanest quantum-advantage evidence yet, and at the *recommended* β.

**SPEED:** D-Wave QPU compute ~60–75 ms and **flat in N**; SA wall 0.2→2.0 s and **grows with N**
(~vars²) → the QPU's compute edge widens with scale. (True wall-clock adds Leap network/queue; not
cleanly captured — the SampleSet resolves lazily. The quality-first race surfaces D-Wave only when it
finds a better portfolio.)

**IN-SAMPLE vs OOS:** D-Wave beats SA on the in-sample objective at ALL sizes (above); the OOS
*benefit* of β-diversification (§7) only kicks in at 40–60. Two distinct things: solver quality
(D-Wave>SA always on the β-objective) vs whether β helps out-of-sample (yes at scale).

## 10. Dynamic β — KEEP IT (right design), refine the fraction
Current: `β = config_fraction × select_objective_scale(problem)` — per-problem dynamic scaling.
- **KEEP:** it makes β's strength RELATIVE to each problem's objective, so "0.25" means the same
  diversification pressure across baskets / γ / sizes (basket-invariant). A fixed ABSOLUTE β would
  dominate some problems and vanish on others → the β sweep would have been noise. The cross-instance
  consistency of all these experiments depends on this dynamic scaling.
- **REFINE:** the optimal FRACTION is N-dependent (marginal ≤30, helps 40–60). The scaling fixes
  objective-MAGNITUDE; the fraction should additionally be N-aware. Enhancement, not a fix.
