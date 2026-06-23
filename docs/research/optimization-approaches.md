# Portfolio Optimization Formulations — Convex QP → QPU-Native

A from-scratch walkthrough of the optimization problem we solve, why the current
one is convex (and therefore classical-natural), and the concrete ways to make
it non-convex **while keeping the player hand-picking the basket**. Math is drawn
out in ASCII, not LaTeX.

Notation used throughout:
- `N` = full asset universe (28).
- `B` = the player's hand-picked basket (a subset of the universe), size `n = |B|`.
- `w_i` = portfolio weight on asset i. `μ_i` = expected return. `Σ` = covariance.
- `γ` = risk aversion (Risk slider). `w_max` = per-asset cap. `w_min` = floor.
- `y_i ∈ {0,1}` = a *selection* bit ("is asset i actually held?").

---

## 0. The single idea that resolves the confusion

There are **two independent questions**. Don't fuse them:

```
   Q1  WHO chooses the assets?         player hand-picks   ⟷   optimizer selects
   Q2  Is the MATH convex?             convex (one basin)  ⟷   non-convex (many)
```

Last turn I described one corner of this grid (optimizer-selects + non-convex)
and made it sound like non-convexity *requires* giving up hand-picking. It does
not. You can sit in the corner **(player hand-picks) × (non-convex)** — that's
the whole point of this doc.

The bridge: **hand-picking decides the candidate pool `B`; non-convexity comes
from the optimizer making discrete choices *inside* `B`** (drop some assets, or
hold exactly k of them). Today those two collapse into one because the basket =
the held set (every picked asset is forced in by the `w_min` floor). The moment
you let the optimizer *drop* or *sub-select* a hand-picked asset, you get
non-convexity for free — and the player is still hand-picking.

---

## 1. Convex vs non-convex — why the QPU cares

**Convex:** the feasible set is "filled in" (any line between two feasible points
stays feasible) and the objective is a single bowl. One global minimum, no
barriers. Gradient methods / interior-point / Gurobi walk straight downhill.

**Non-convex:** the feasible set has holes or is a scatter of disconnected pieces
(discrete choices), so the energy landscape fractures into many local minima
separated by barriers.

```
   CONVEX (today)                 NON-CONVEX (selection / cardinality)

   E |\                  /        E |   .          .        .
     | \                /           |  / \   .--. / \   .  / \
     |  \              /            | /   \ /    v   \ / \/   \
     |   \____________/             |/     v          v       \
     |     one basin                |   many basins + barriers
     +------------------ w          +---------------------- choice
        ↑ classical nails it           ↑ tunneling can cut through barriers
```

Quantum annealing's *only* theoretical edge is tunneling **through** those
barriers instead of climbing over them (as thermal SA must). No barriers ⟹ no
edge. So "make it QPU-native" literally means "give the landscape barriers,"
i.e. make it non-convex/combinatorial.

---

## 2. Method 0 — the current problem (continuous convex QP)

```
   minimize   f(w) = (γ/2)·wᵀ Σ w  −  μᵀw          over the basket B (n assets)
      w
   subject to Σ_i w_i = 1                           (budget)
              w_min ≤ w_i ≤ w_max   for all i ∈ B   (box — note: LOWER bound forces
                                                      every basket asset to be held)
```

**Convexity (why it's a single bowl):**

```
   Hessian ∇²f = γ·Σ
   γ > 0,   Σ ≻ 0  (covariance.py floors eigenvalues > 0)
   ⟹ γΣ ≻ 0  ⟹ f strictly convex.
   Feasible set = simplex ∩ box = convex polytope.
   ⟹ unique global optimum.
```

- **Who picks:** player hand-picks B, and B = exactly the held set (the `w_min`
  floor forbids dropping any of them).
- **QPU fit:** poor. The QUBO we ship is just a *bit-discretization of this bowl*
  — combinatorial in form but smooth in substance, one basin. SA and QPU sample
  the same basin; the race is fair but the problem gives quantum nothing.
- **`w_min`'s role here:** purely cosmetic participation — "don't give a picked
  asset ~0." It is *not* load-bearing. (This is the floor you flagged.)

This is the baseline every method below modifies.

---

## 3. Where non-convexity can be injected (three sources)

```
   (a) CARDINALITY:        hold exactly k of the candidates    Σ y_i = k
   (b) SEMI-CONTINUOUS:    each weight is 0 OR ≥ w_min         w_i ∈ {0} ∪ [w_min, w_max]
   (c) FRUSTRATED OBJECTIVE: reward/penalize combinations      (diversification, sectors…)
```

(a) and (b) are *selection* non-convexities — they make `w_min` meaningful and
let the optimizer curate **inside the player's basket**. (c) deepens the
ruggedness regardless of who picks. All three are compatible with hand-picking.

---

## 4. Method 1 — semi-continuous weights inside the basket  ★ keeps hand-pick, minimal change

**The one change:** replace the hard floor `w_min ≤ w_i` with a *conditional*
floor — an asset is either **out (0)** or **in at ≥ w_min**:

```
   minimize   (γ/2)·wᵀΣw − μᵀw
   subject to Σ_i w_i = 1
              w_min·y_i ≤ w_i ≤ w_max·y_i      (y_i=0 ⟹ w_i=0 ; y_i=1 ⟹ w_i∈[w_min,w_max])
              y_i ∈ {0,1},   i ∈ B
```

**Why non-convex:** each weight now lives in `{0} ∪ [w_min, w_max]` — a
*disconnected* set (a hole between 0 and w_min). A union of disjoint intervals is
the textbook non-convex feasible region. With the binaries `y` it's a
Mixed-Integer QP (NP-hard).

```
   feasible w_i:   ●────────hole────────[============]
                   0                  w_min        w_max
                   "out"              "minimum buy-in if you're in"
```

- **Who picks:** player hand-picks B (the candidate pool); the optimizer decides
  **which of them actually make the cut** and at what weight. Hand-picking fully
  preserved; the pick now *means* something (the optimizer can reject a pick).
- **`w_min` becomes load-bearing:** it's now a real *minimum buy-in* — the thing
  that forces sparsity. This is exactly the role you intuited for it.
- **No new slider, no UX redesign.** Sparsity is *endogenous* — the optimizer
  chooses how many names to hold based on risk/return; you don't set k. The only
  UX change is "the optimizer may not use all your picks."
- **QUBO size:** `n` selection bits + `n·b` weight bits + linking penalties
  (`x_ik ≤ y_i`, budget, semicontinuous link). For n=25, b=2 ≈ 75 vars + dense
  penalties → **back near the precision wall** from the QPU tuning work.
- **QPU fit:** genuinely non-convex, but the weight bits make it big; on
  Advantage this is the hard regime. Classically (Gurobi MIQP / SA) it's still
  easy at n≤28.

---

## 5. Method 2 — cardinality sub-selection, equal weight  ★ keeps hand-pick, chip-friendly sweet spot

Hold **exactly k** of the player's n basket assets, equally weighted
(`w_i = y_i / k`). Substituting collapses the whole thing to a pure binary
problem in `y`:

```
   minimize   (γ / 2k²)·Σ_{i,j} Σ_ij · y_i y_j   −   (1/k)·Σ_i μ_i y_i
      y
   subject to Σ_i y_i = k,   y_i ∈ {0,1},   i ∈ B

   QUBO:  add  λ·(Σ_i y_i − k)²       →   n binary variables (one per basket asset)
```

- **Who picks:** player hand-picks B; optimizer picks **which k of them**. Hand-
  picking preserved.
- **Why non-convex:** cardinality `Σy=k` is a combinatorial constraint; the
  feasible set is `C(n,k)` discrete points, not a polytope. Pure selection.
- **It's a frustrated Ising model:** couplings `J_ij = Σ_ij` make correlated
  assets "repel" in a low-risk set while high-μ assets "attract" — competing
  pulls ⟹ rugged landscape ⟹ tunneling has something to do.
- **Do the sliders still mean anything with equal weights? Yes:**
  - `γ` (Risk) decides **which subset**: high γ → low-variance / anti-correlated
    names; low γ → highest-return names. Still fully meaningful.
  - `k` (cardinality) = "how concentrated." Map the **Max-Position slider → k**
    (high max-position → small k → concentrated), or add a "How many to hold"
    control. Either way it's the diversification dial you dropped earlier,
    reincarnated as the constraint the QPU enforces.
- **QUBO size:** just `n` binaries (≈25). Short chains, leaves the chip's
  dynamic range for the objective → **this also fixes the feasibility/precision
  problem** from the tuning work. Small, clean, non-convex.
- **Cost:** equal weights — the optimizer no longer fine-tunes magnitudes, only
  membership. For a booth ("the quantum computer picks the best k of your
  watchlist") that's arguably clearer, not worse.

---

## 6. Method 3 — cardinality + semi-continuous (the full classic MIQP)  keeps hand-pick

Combine 1 and 2: optimizer picks the subset **and** the weights.

```
   minimize   (γ/2)·wᵀΣw − μᵀw
   subject to Σ w_i = 1,   Σ y_i = k
              w_min·y_i ≤ w_i ≤ w_max·y_i,   y_i ∈ {0,1},   i ∈ B
```

This is the canonical **cardinality-constrained semi-continuous Markowitz
problem** — the genuinely hard, non-convex one studied in the literature.
Richest, most "real." But as a QUBO it's `n + n·b` binaries + the most penalty
terms → biggest and most precision-hungry. Keeps hand-picking. Best left for
later if Method 2 proves too coarse.

---

## 7. Method 4 — optimizer selects from the whole universe  ✗ DROPS hand-pick (contrast only)

Identical math to Method 2/3 but with `i` ranging over the **entire universe N**,
not the player's basket. This is the version that **removes hand-picking** (the
player only sets sliders; the optimizer chooses from all 28). Included so the
axis is clear: the *only* difference between "keeps hand-pick" and "drops hand-
pick" is whether the index set is `B` (player's pick) or `N` (universe). You want
`B`. Everything in Methods 1–3 already uses `B`.

---

## 8. Frustration and the diversification reward — making it genuinely *rugged*

Non-convex ≠ hard. At n≤28 even the cardinality problem is classically trivial
(SA/Gurobi solve it in ms), so without extra structure you get a *legitimate* QPU
problem but not a measurable quantum *advantage*. "Frustration" is how you deepen
the landscape so tunneling has something to do. (Deferred for now per the working
plan — captured here for later.)

### What frustration is

A spin-glass term: a system is **frustrated** when you cannot simultaneously
satisfy all the pairwise preferences. The canonical picture is three spins on a
triangle that each "want" to be opposite their neighbours — on a loop of three,
someone always loses. The consequence is **many competing near-optimal
configurations separated by barriers** — exactly the rugged, multi-basin
landscape annealing is built for.

In selection terms the objective already has competing pieces: pairwise risk
terms `Σ_ij y_i y_j` (correlated assets "repel") versus linear return terms
`μ_i y_i` (high-return assets "attract"). A **diversification reward** is an
*extra* pairwise term added on purpose to deepen that conflict:

```
   add to the objective:   + β · Σ_{i<j}  ρ_ij · y_i y_j        (ρ_ij = correlation)

   ρ_ij > 0 (correlated pair)      → positive cost → discourages holding both
   ρ_ij < 0 (anti-correlated pair) → negative cost → rewards holding both
   β  = the "frustration knob" — tunable INDEPENDENTLY of risk aversion γ, and
        it adds NO new variables (just n(n−1)/2 extra couplings).
```

### Why it makes barriers — the frustrated triangle (concrete)

Three assets, pick `k = 2`, with correlations:

```
   ρ_AB = −0.5   (A,B diversify well)
   ρ_BC = −0.5   (B,C diversify well)
   ρ_AC = +0.5   (A,C redundant)

   energy of each 2-subset (just the β term):
     {A,B}: β·(−0.5) = −0.5β   ← good
     {B,C}: β·(−0.5) = −0.5β   ← good (tied)
     {A,C}: β·(+0.5) = +0.5β   ← bad
```

Two equally-good optima, `{A,B}` and `{B,C}`. To move between them you must
**swap A→C**, but a single bit-flip breaks `k=2`, so every one-flip path passes
through `{B}` (k=1) or `{A,B,C}` (k=3) — both penalised by the cardinality term.
That penalised in-between state **is the barrier**:

```
   energy
     |  {A,B}\        barrier (k≠2)        /{B,C}
     |        \______/\__________/\_______/
     +------------------------------------------ configuration
        SA must thermally CLIMB the barrier; the QPU can TUNNEL through it.
```

Cardinality *alone* already creates these swap-barriers; the diversification
reward **multiplies how many exist and how deep they are** (every frustrated
triangle adds basins), turning a mildly bumpy landscape into a glassy one. That
is why β is a "knob": dial it up until the QPU's tunneling can reach optima that
SA's hill-climbing gets stuck away from.

### Honest caveat (overlap with the risk term)

The mean-variance risk term `wᵀΣw` already penalises correlated *positions*
(weighted by size). The diversification term penalises correlated *membership*
(binary, size-independent), with its own coefficient β. Related but distinct
levers — risk says "don't put much *weight* in correlated names," diversification
says "don't even *hold* them together." Keeping them separate lets you crank
frustration without also cranking risk aversion.

### In Method 3 it slots straight in

```
   min  (γ/2)·wᵀΣw − μᵀw  +  β·Σ_{i<j} ρ_ij·y_i y_j
   s.t. Σ w_i = 1,  Σ y_i = k,  w_i ∈ {0} ∪ [w_min,w_max] linked to y_i
        (i over the player's hand-picked basket B)
```

— frustration on the *selection* layer, on top of the weight optimisation.

### Other frustration knobs (same family)

```
   • Sector caps:           Σ_{i∈sector_s} y_i ≤ m_s   (combinatorial side-constraints)
   • Target-return floor:   Σ_i μ_i w_i ≥ r_target      (cuts the feasible set non-trivially)
   • Bigger candidate pool: players pick from a 100–500 name universe (selection space explodes)
```

The diversification reward is the highest-leverage: competing pairwise couplings,
no extra variables.

---

## 9. Encoding the weight grid cleanly (integer-units)

This is upstream of QPU *parameter* tuning: it shapes how exactly the weights and
the budget can be represented at all. It matters most for the weighted methods
(1 and 3).

### The problem with the current grid

```
   w_i = w_min + c·Σ_k 2^k x_ik ,     c = (w_max − w_min) / (2^b − 1)
                                                          └── NOT a power of two
```

Because of that `2^b − 1` denominator, weights land on ugly values **and Σw = 1
is generally not exactly reachable on the grid**. That is why the pipeline leans
on the normalize-and-hope step, and why the budget penalty has to be strong (it
is chasing a target the lattice cannot hit). Both waste the chip's finite
precision.

### The fix: distribute a fixed number of integer "units"

```
   pick a total budget of  M = 2^m  units  (e.g. M = 16 or 32)
   each asset gets an integer  u_i  units ;   weight  w_i = u_i / M

   budget:   Σ_i u_i = M                 ← exact integer; a real lattice point HITS it
   box:      u_min ≤ u_i ≤ u_max         ← integer bounds
   semi-cont (Method 3):  u_i ∈ {0} ∪ {u_min,…,u_max}
   encode:   u_i = y_i·u_min + Σ_k 2^k x_ik     (y_i selects, x bits add units above the floor)
```

Concrete clean instance — `M = 16`, `u_min = 2`, `u_max = 8`:

```
   held weights land on  {2/16, …, 8/16} = {12.5%, …, 50%}   (dyadic, exact)
   budget Σu = 16 is exactly hittable:   8+8,  4+4+4+4,  2+6+8, …
```

### Which slider values to make "clean," and which don't matter

```
   Max-Position  → u_max  (integer units)   ★ make clean: e.g. {2,4,8} units = {12.5%,25%,50%}
   Min buy-in    → u_min  (integer units)   ★ make clean: {1,2}
   Cardinality k → integer                  already clean
   Total M       → 2^m (16 or 32)           ★ master dial: bigger M = finer weights, more bits
   Risk γ        → a scalar multiplier      ✗ does NOT need to be clean — the chip auto-scales the
                                              whole objective, so γ never touches the grid
   Rebalance     → schedule only            ✗ irrelevant to encoding
```

Rule of thumb: **anything that defines the weight *lattice* (M, u_max, u_min, k)
should be integers / powers of two; anything that is just a *coefficient* (γ, β)
can be any real** — it scales energies, not the grid.

### Why this helps precision (the chain, stated honestly)

```
   1. Σu = M is exactly representable  →  a feasible read EXISTS on the lattice
                                          →  drop the normalize-and-hope crutch.
   2. The budget penalty now targets a REACHABLE minimum  →  it can be SMALLER/sharper.
   3. A smaller budget penalty stops hogging the chip's dynamic range
                                          →  more resolution left for the objective  →  better precision.
```

The big win is #1–#2 (exact feasibility, smaller penalty); cleaner dyadic
coefficients are a *secondary* help — the chip auto-scales to [−1,1] regardless,
so "nice numbers" alone don't buy precision. The real lever is **exact budget
representability**, which integer-units gives for free, and which is also the
cleanest answer to "handle the budget for better QPU precision." Cost: coarser
slider granularity (max-position only takes `u_max/M` values) — fine for a game.

---

## 10. Side-by-side

```
 Method                     Who picks      Convex?   Vars (n=25,b=2)   QPU-native   Chip size   New UX?
 ────────────────────────── ───────────── ───────── ───────────────── ──────────── ─────────── ────────
 0  current convex QP        player         CONVEX    50 weight bits     no           ok          —
 1  semi-continuous wts      player         non-cvx   ~75 (sel+wts)      yes          large       low
 2  cardinality, eq-weight   player         non-cvx   ~25 (sel only)     yes          small ★     small (k)
 3  cardinality + semi-cont  player         non-cvx   ~75+               yes          large       med
 4  select from universe     OPTIMIZER      non-cvx   ~28 (eq-wt)        yes          small       large
 8  + frustration knobs      either         non-cvx   (same)             yes++        same        varies
```

★ Method 2 is the only row that is **(player hand-picks) AND (non-convex) AND
(small/chip-friendly)** at once.

---

## 11. Recommendation for *your* constraint (keep hand-pick + non-convex)

1. **Make Method 2 the core.** Player hand-picks the basket `B`; the optimizer
   selects the best **k of B**, equal-weighted. It is the minimal move that is
   simultaneously: hand-pick-preserving, genuinely non-convex, and small enough
   that the QPU performs *well* (fixing the earlier precision/feasibility wall).
   Sliders stay meaningful (γ → which subset, k → how many).

2. **Add the diversification reward (the §8 frustration knob)** to make the
   landscape rugged enough that the QPU's tunneling can actually diverge from SA —
   free in variable count. (Deferred for now.)

3. **Hold Method 1/3 (weighted) in reserve** — if equal-weight feels too coarse,
   bit-encode weights on the *selected* assets only. It's richer but re-enters
   the precision wall, so adopt only if Method 2's equal weighting is a real
   product limitation.

The decision that gates all of this is the **product one**: today a player's
basket = exactly what they hold. Methods 1–3 change that to *candidate pool* — the
optimizer may **drop** some of their picks. That's the meaning of "non-convex
while hand-picking." If you're comfortable with "the optimizer curates within
your picks," Method 2 is the clean path.

---

### Quick mental model to keep

```
   hand-pick  = you choose the CANDIDATE POOL  (the index set the optimizer sees)
   non-convex = the optimizer makes DISCRETE choices INSIDE that pool
                (drop assets / hold exactly k)
   today they're fused (pool = held set); un-fuse them and you get both.
```

---

## 12. Worked example — seeing convex vs non-convex with real numbers

Five hand-picked assets, `γ = 3`. Covariance `Σ_ij = ρ_ij·σ_i·σ_j`:

```
   asset   μ      σ        correlations ρ
   BTC     0.10   0.40     BTC  ETH  NVDA  GLD   TLT
   ETH     0.12   0.45     1.00 0.85 0.50 -0.10 -0.30
   NVDA    0.08   0.30          1.00 0.45 -0.10 -0.30
   GLD     0.03   0.15               1.00  0.00 -0.20
   TLT     0.02   0.10                     1.00  0.30
                                                 1.00
   (BTC/ETH/NVDA = correlated growth; GLD/TLT = diversifiers, anti-corr to crypto)
```

### Method 0 — continuous convex QP (today). One basin, all held.

```
   w* = BTC 1.7%  ETH 15.0%  NVDA 16.6%  GLD 20.8%  TLT 45.8%     obj = −0.03079
   unique global minimum; every asset gets a weight; smooth — classical nails it.
```

### Method 2 — cardinality k=3, equal weight. The selection QUBO (5 binaries).

`H(y) = (γ/2k²)·yᵀΣy − (1/k)·μᵀy + λ(Σy−k)²`, with `λ=0.5`, `k=3`:

```
   Q (quadratic, symmetric)                       linear (on the diagonal)
   [0.527 0.526 0.510 0.499 0.498]                [−3.033 −3.040 −3.027 −3.010 −3.007]
   [0.526 0.534 0.510 0.499 0.498]
   [0.510 0.510 0.515 0.500 0.499]                (the near-uniform ~0.5 off-diagonals
   [0.499 0.499 0.500 0.504 0.501]                 are the cardinality penalty; the
   [0.498 0.498 0.499 0.501 0.502]                 structure lives in the small differences)
```

Enumerating all C(5,3)=10 subsets by true objective (equal weight):

```
   NVDA,GLD,TLT  −0.02342   ← best        BTC,NVDA,GLD  −0.00658
   ETH,GLD,TLT   −0.02275               ETH,NVDA,GLD  −0.00617
   BTC,GLD,TLT   −0.02242               BTC,ETH,TLT   +0.02458
   BTC,NVDA,TLT  −0.00933               BTC,ETH,GLD   +0.02758
   ETH,NVDA,TLT  −0.00917               BTC,ETH,NVDA  +0.06667   ← worst (all-correlated)
```

### Method 3 — cardinality k=3 + integer units (M=16, u∈[2,8]). Weights re-rank it.

Best integer-unit allocation per subset (each = best of Σu=16, u∈[2,8]):

```
   ETH,GLD,TLT   −0.02730   units (4,4,8) = 25% / 25% / 50%   ← best
   ETH,NVDA,TLT  −0.02582   units (3,5,8)
   BTC,GLD,TLT   −0.02558   units (4,4,8)
   NVDA,GLD,TLT  −0.02407   units (5,4,7)
   …
   BTC,ETH,NVDA  +0.04622   units (5,3,8)                     ← worst
```

Note the **ranking changed vs equal-weight**: weight optimisation lets
`ETH,GLD,TLT` overtake `NVDA,GLD,TLT` by loading 50% into low-risk TLT. That extra
freedom is exactly what Method 3 buys over Method 2 — and what costs the extra
`n·b` variables on the chip.

### The honest punchline: non-convex ≠ rugged

Under single-asset **swap** moves, this realistic instance has **exactly one local
optimum** (`ETH,GLD,TLT`) — even after adding the diversification term at β up to
0.12. Cardinality made the problem **discrete/combinatorial** (the right *shape*
for a QUBO/QPU), but the landscape is still effectively **single-basin**, because
GLD/TLT are *universal* diversifiers every good subset wants — there is no
competing triangle. A single basin is still classically easy; tunneling has
nothing to bite on.

**Ruggedness needs *competing* structure.** Minimal example that produces it — four
assets, two "good pairs" `{A,B}`,`{C,D}` (ρ=−0.6 within) that are hostile across
(ρ=+0.5), pick k=2:

```
   A,B  −0.03300  ← LOCAL OPT          A,C  +0.04125
   C,D  −0.03300  ← LOCAL OPT          A,D  +0.04125
                                       B,C  +0.04125
                                       B,D  +0.04125
   TWO basins. To swap {A,B} → {C,D} every one-swap path crosses a hostile
   cross-pair (+0.041, strictly worse) = the BARRIER. SA must climb it; a QPU
   can tunnel. THIS is where quantum has something to do.
```

**Takeaway:** cardinality (Methods 2/3) is necessary for QPU-relevance (it makes
the problem non-convex/discrete), but **not sufficient for ruggedness** — that
comes from frustrated/competing correlations, which the deferred β knob (§8) and a
suitably structured/large universe deliberately inject. Method 3 gives you the
right shape; frustration is what later makes the QPU *shine* on it.
