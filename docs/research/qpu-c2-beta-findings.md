# QPU encoding & the D-Wave-vs-SA result — C2 + β findings

Untracked working notes. Real data = asset-tracker.quip.network (assets-api). 2026-06-21.
Status: **experiments complete; implementation (wire C2+β into the solver path) being planned.**
Companion log: `qpu-encoding-investigation.md` (chronological detail).

---

## TL;DR

On the cardinality-constrained portfolio problem the QPU underperformed because of the
**encoding**, not the hardware. The fix — **C2** (penalty-free *selection* QUBO + greedy projector
+ convex QP weights) — makes **both** SA and D-Wave hit the Gurobi optimum. But on the default
(smooth) objective they **tie** and SA is faster: a smooth problem has nothing for the QPU to
exploit. Adding the **β diversification term** makes the selection landscape **rugged**, and there
**D-Wave decisively beats SA on quality** (3/3 repeats, 18–28 assets), with SA trapped in a local
minimum it **cannot escape with 100× more compute**. Caveat: this is vs SA (`dwave-neal`); parallel
tempering is untested.

**The two ingredients are both necessary:** clean encoding (removes the feasibility handicap) AND
β (supplies the ruggedness). Neither alone shows the advantage.

---

## 1. The problem — Method 3 (cardinality + semi-continuous MIQP)

```
   min over (S, w)   (γ/2)·wᵀΣw − μᵀw
        S = which K assets are held   (integer / combinatorial)
        w = their weights             (continuous)
   s.t. Σw = 1,  exactly K held,  w_min ≤ w_i ≤ w_max on held
```

Splits into an **outer** combinatorial selection (which K — non-convex, the hard part) wrapped
around an **inner** convex QP (the weights — one bowl, trivial). The QPU's only relevant job is the
outer selection; the weights belong to a classical solver.

## 2. The encoding journey

- **Penalized (the original bug):** fold both equality constraints into the QUBO as penalties.
  Cardinality `(Σy−K)²` is a dense rank-one term = a COMPLETE GRAPH on the select bits (a clique).
  On D-Wave that means long embedding chains → only ~2–10% of reads land feasible. It handicaps
  ONLY the QPU (SA runs the logical QUBO in float64 — no embedding, ~100% feasible). So SA wins
  every race purely because the encoding cripples its competitor.
- **Penalty-free:** drop the cardinality penalty; sample an objective-only sparse QUBO; enforce
  exactly-K classically. Matches the 2026 paper arXiv:2605.17628 (independently).
- **Selection-only (C2):** binary indicator per asset, no weight bits. Smallest, sparsest QUBO.

## 3. C2 vs C3 — the encoding ablation (penalty-free vs keep the penalty)

Both over binary selection x∈{0,1}ᴺ, equal-weight (1/K) surrogate objective:
```
   obj(x) = −Σ μ_i x_i / K  +  (γ/2K²)·Σ_ij Σ_ij x_i x_j        (return − risk)
   C2 (penalty-free): objective only → greedy-project to exactly K
   C3 (cardinality):  + A·(Σx − K)²  → K enforced in the QUBO
```

Result (real data, best-of-500 + QP weights, gap to Gurobi MIQP optimum):

| size  | C2 (penalty-free) | C3 (cardinality penalty) |
|-------|-------------------|--------------------------|
| 12a/K5| ~0% (optimal)     | ~0% (tie — too small)    |
| 18a/K6| **0%** exact supp | 1.5–2.5% short           |
| 28a/K8| **0%** exact supp | 1.7–2.8% short           |

C3 penalty sweep at 28a: gap NEVER reaches 0 at any strength (0.6–2.5%); only penalty=0 (=C2) does.
**Cause = objective washout, not chain breaks** (C3 chain breaks ~0%): the large penalty needed to
enforce K dominates the energy, so the finance objective becomes a tiny perturbation → solver lands
on feasible-but-suboptimal subsets. Verdict: **adopt C2, drop C3.**

## 4. The hybrid pipeline (adopted)

```
   sliders → PortfolioProblem(μ,Σ,γ,w_max,K[,β])
        │
        ▼   risk preference γ + market (μ,Σ)  →  into the QUBO
   objective-only SELECTION QUBO  (N binary bits, sparse)   ← C2 (+β coupling, §5)
        │  same QUBO to both racers
        ▼
   SA (neal, 500 reads)        D-Wave (Pegasus clique, 500 reads, 20µs, ×3 chain)
        │  bitstrings                │  bitstrings
        ▼                            ▼
   CLASSICAL FINISH (shared, EVERY read):
     1. greedy projector → exactly K assets          ← cardinality K (classical)
     2. optimal_weights QP on the K  (Σw=1, box)     ← weights w_max, budget (classical)
        │
        ▼  score by TRUE objective p.objective(w)
   winner = best portfolio (quality);  time reported alongside
```

- `optimal_weights` (financial/weighting.py) validated: reproduces Gurobi's objective on a fixed
  support to <1e-18. It fixed the old 12-asset gap (21% with crude renormalize → **0%** with the QP).
- Greedy projector: repairs every read to exactly K (drop weakest / add best by surrogate value).
  Measured == EXACT best-K-of-pool enumeration at booth scale (greedy myopia costs 0). The
  combinatorial search is the SAMPLER's (it prunes 28→14 candidate assets); the projector just
  finalizes the count. **Feasibility is 100% by construction for both solvers** — this is what
  removes the prior feasibility confound.

## 5. The β term — WHAT IT ADDS (diversification, via anti-correlation)

```
   added to the objective:   + β·Σ_{i<j} ρ_ij · y_i · y_j        ρ_ij = Σ_ij / √(Σ_ii·Σ_jj)
```

ρ is the CORRELATION matrix. Reading the term:
- ρ_ij > 0 (assets move together)  → +β·ρ added to the minimized objective → **penalizes** co-holding
- ρ_ij < 0 (assets move oppositely) → −β·ρ → **rewards** co-holding
- ρ_ij ≈ 0                          → no effect

So **mechanically it is an ANTI-CORRELATION term** (penalize correlated pairs, reward anti-correlated
pairs); its **goal/effect is DIVERSIFICATION** (a decorrelated basket). They are the same lever seen
two ways — *diversification is what the anti-correlation reward produces*. In our universe
(correlations mostly positive) it acts mainly as "penalize holding correlated assets together" →
push toward the least-correlated K-subset.

**Why it is distinct from the variance term** and why it MATTERS: the risk term `(γ/2)wᵀΣw` already
penalizes total portfolio variance (correlation weighted by variances/weights, traded against
return). β adds an **explicit per-pair correlation pressure on the SELECTION**, regardless of
variance/return. That competes with return-seeking (an asset great for return may be penalized for
correlating with another held one) → **competing pulls = FRUSTRATION = a rugged landscape with many
local minima.** That ruggedness is the regime a QPU can exploit (tunnel between basins) and where SA
gets trapped.

NOTE: β is NOT a quantum trick — it is a legitimate portfolio objective (decorrelated/diversified
basket). It also *changes the problem* (trades some return for diversification), so it is a product
choice, exposed as the `METHOD3_FRUSTRATION_BETA` knob.

## 6. THE RESULT — D-Wave beats SA on the rugged (β>0) landscape

Fair re-test: C2+β, every read repaired for BOTH solvers (best-of-500 vs best-of-500), Gurobi-β
MIQP oracle, ×3 chain, 20µs, 500 reads, β = frac×base (base = max|C2 coeff|), 3 repeats, real data.
gap% = to the Gurobi-β optimum (lower=better); DWwin = # of 3 repeats D-Wave strictly beats SA.

| size  | β/base | SA gap% | DW gap% | DWwin | SA uniq | DW uniq |
|-------|--------|---------|---------|-------|---------|---------|
| 12a   | all    | 0.00    | 0.00    | 0/3   | 1       | 1–23    |  (too small to differ)
| 18a   | 0.00   | 0.00    | 0.00    | 0/3   | 1       | 4       |
| 18a   | 0.25   | 46.45   | **0.00**| **3/3**| 1      | 34      |
| 18a   | 0.50   | 113.73  | **0.00**| **3/3**| 1      | 78      |
| 18a   | 1.00   | 0.00    | 0.00    | 0/3   | 2       | 122     |  (high β → easy again)
| 18a   | 2.00   | 0.00    | 0.00    | 0/3   | 4       | 163     |
| 28a   | 0.00   | 0.04    | 0.00    | 3/3   | 1       | 9       |
| 28a   | 0.25   | 3.51    | **0.00**| **3/3**| 1      | 113     |
| 28a   | 0.50   | 1.20    | **0.00**| **3/3**| 2      | 194     |
| 28a   | 1.00   | 4.41    | **0.00**| **3/3**| 1      | 277     |
| 28a   | 2.00   | 4.06    | **0.00**| **3/3**| 1      | 362     |

- β=0 (smooth): tie (both optimal), SA faster. **The QPU needs ruggedness.**
- β>0 (rugged): **D-Wave optimal at every β; SA trapped 1.2–4.4% off (28a) / 46–113% off (18a band).**

## 7. Robustness — SA is genuinely trapped, NOT under-powered

SA given up to 100× sweeps and 4× reads; D-Wave fixed (500 reads, 20µs):

| SA config (18a, β/base=0.5) | SA gap% | time | uniq | D-Wave |
|-----------------------------|---------|------|------|--------|
| 500r × 1,000 sw             | 113.73  | 0.04s| 1    | **0.00% in 0.056s** |
| 500r × 5,000 sw             | 113.73  | 0.20s| 1    | |
| 500r × 20,000 sw            | 113.73  | 0.79s| 1    | |
| 500r × 100,000 sw           | 113.73  | 3.87s| 1    | |
| 2,000r × 20,000 sw          | 113.73  | 3.15s| 1    | |

SA's gap is **completely invariant to compute** (uniq=1 always — same local min every run). Same at
28a/β1.0: SA stuck at 4.41% from 0.05s to 4.3s; D-Wave 0.00% in 0.058s (~70× faster, optimal).

## 8. Mechanism

SA converges to ONE deceptive basin (uniq=1) and more sweeps just descend deeper into the SAME
basin. D-Wave's quantum sampling explores 34–362 distinct subsets (uniq) and reaches the global
optimum — sample diversity / tunneling is the advantage. Chain breaks low (0–4.6%), oracle dev
~1e-19 (scoring validated). So it is genuine solution quality on the rugged landscape, not a
feasibility/chain/scoring artifact.

## 9. Honest caveats

1. **vs SA (dwave-neal)** — the booth race's classical solver. **Parallel tempering / tabu**
   (built for rugged landscapes) are UNTESTED and might also escape. Demonstrated advantage over
   SA, NOT proven vs all classical. → Next rigor frontier.
2. **β changes the problem** (adds diversification — a real portfolio goal). Advantage exists only
   where β makes it rugged; β=0 ties. High β (≳1×scale at 18a) becomes easy again.
3. **Speed:** SA still slightly faster (0.04 vs 0.058s). A race scored purely on "fastest feasible"
   would still pick SA despite a worse portfolio → the booth must score on **portfolio quality**
   (best objective), reporting time alongside.
4. 18a's 113% is on a near-zero-magnitude objective (β nearly cancels risk−return); **28a (1.2–4.4%,
   clean magnitude, unescapable) is the solid evidence.**

## 10. Decision & next steps

- **Adopt C2** (penalty-free selection QUBO + greedy projector + convex QP weights). Drop C3.
- **Expose β** (`METHOD3_FRUSTRATION_BETA`) as the diversification/ruggedness knob; ~0.25–0.5×scale
  is the band where D-Wave wins at 18–28 assets.
- **Wire C2+β into the solver path**; **score the race on portfolio quality (best objective), report
  time alongside.** (Implementation plan to follow.)
- **Later:** re-test the advantage vs parallel tempering (hardens the claim).
```
