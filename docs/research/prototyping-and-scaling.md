# Prototyping & scaling — research handoff

Entry point for picking up the optimization research. Pairs with the consolidated findings in
[`qpu-experiment-synthesis-2026-06-22.md`](qpu-experiment-synthesis-2026-06-22.md) (sections cited as
§N below) and the reproducible harnesses in [`scripts/`](scripts/).

## Vocabulary (post-rename — use these terms)
- **cardinality mode** — `OPTIMIZATION_MODE="cardinality"` (was `method3`). Pick exactly **K** of the
  basket; semi-continuous weights. The default mode. `problem.is_cardinality` is the predicate.
- **select encoding** — `CARDINALITY_ENCODING="select"` (default). Penalty-free **N-bit selection**
  QUBO (one bit/asset, objective + β only) → **greedy projector** to exactly-K → **convex QP**
  (`financial.weighting.optimal_weights`) for the weights. The QPU only chooses *which* assets;
  cardinality + weights are classical, so every read is feasible. `DecodeMeta.scheme="select"`.
- **penalized encoding** — `CARDINALITY_ENCODING="penalized"` (legacy, `encode_penalized`,
  `scheme="penalized"`). Integer-units QUBO with budget+cardinality+linking penalties.
  **Superseded** — the penalty's dense clique washes the objective out below QPU precision (§2);
  kept only as a fallback and is a **removal candidate**.
- **convex mode** — `OPTIMIZATION_MODE="convex"`. Mean-variance box-QP, every basket asset held (no
  cardinality). Legitimate fallback.
- **β (diversification)** — `CARDINALITY_FRUSTRATION_BETA` (peak fraction of the objective scale),
  the reward `+β·Σ_{i<j} ρ_ij x_i x_j` on the selection. **N-aware ramp**: 0 below
  `CARDINALITY_BETA_N_MIN` (12), full at/above `CARDINALITY_BETA_N_FULL` (40). It is what makes the
  selection landscape *rugged* → where the QPU out-searches classical.
- Providers: **SA** (neal, CPU), **D-Wave** (Pegasus clique sampler, QPU), **Gurobi** (exact MIQP
  oracle — dev-only, `GUROBI_IN_RACE`). Winner = best `problem.objective` (lowest), tie-broken by
  speed within `RACE_WINNER_OBJECTIVE_TOL` (`RACE_WINNER_BY="objective"`).

## Current state (on `deployment-dev`)
Validated + shipped: select encoding (default), N-aware β, quality-first race, the K≈N/3 frontend
guardrail, backend hardening. **Open research directions are below.**

## Reproduction
- Env: `backend/.venv` (no uv). Real data: `MARKET_DATA_SOURCE=assets-api`,
  `ASSETS_API_BASE_URL=https://asset-tracker.quip.network`. D-Wave needs `DWAVE_API_TOKEN` (the
  harnesses read `dwave-key.txt` at repo root — **gitignored; never commit**).
- Scripts in `scripts/` have **hardcoded `ROOT=/Users/azainmac/...` paths** — adjust before running.
  They `import backend`, so run from `backend/` (or set `PYTHONPATH=backend/src`).
- Yahoo universe (for N>28): `pip install yfinance` (already in the venv); daily bars, winsorize
  returns at ±50% (illiquid-alt spikes corrupt the covariance — §7).
- **QPU quota**: D-Wave free tier ≈1 min/month; each call ≈60–75 ms. Bound every QPU run
  (`MAX_QPU_CALLS`); the harnesses only call D-Wave on rugged cells.

---

## Direction A — alternative objectives (better out-of-sample)

The deep finding (§ objective discussion): plain **mean-variance is μ-driven → smooth (no QPU edge)
AND fragile out-of-sample** (it over-fits noisy return estimates). Shifting weight onto
**diversification / correlation structure** makes the landscape *rugged* (QPU wins) AND *more robust
OOS* — the same move buys both. Two concrete prototypes:

### A1. MaxDiv — μ-free max-diversification selection  ⭐ most promising
- **What:** select the K *least-correlated* assets (minimize `Σ_{i<j∈S} ρ_ij`), μ-free; weight equally
  or by min-variance. It's a max-dispersion problem — the most QPU-native objective of the set.
- **Results so far** (§5, §7): **25–45% lower OOS volatility everywhere**, competitive-to-best Sharpe
  (best at 15a; 30a 0.030, 40a 0.045 — top of the field), wins 5–6/8 windows vs MV-β0. μ-free → no
  estimation-error. (One 48-asset cell blew up on a Yahoo data outlier — winsorize first.)
- **Prototype:** add a selection-objective seam — e.g. `SELECT_OBJECTIVE = "mean_variance" | "maxdiv"
  | "blend"` (a `(1−α)·MV + α·correlation` mix). `encode_select` builds the surrogate; a maxdiv
  variant zeroes the μ/own-variance diagonal and uses ρ for the pairwise term. `greedy_project`
  already takes a surrogate, so the projector reuses cleanly. A greedy `greedy_maxdiv` reference is in
  `scripts/qtw_beta_backtest_yahoo.py`.
- **Test:** extend the OOS backtest (`scripts/qtw_beta_backtest_yahoo.py`) with maxdiv as a method
  (already present) on a winsorized universe; then a bounded SA-vs-D-Wave run
  (`scripts/qtw_scale_qpu.py` pattern) — maxdiv should be rugged → confirm the QPU wins.
- **Acceptance:** OOS Sharpe ≥ MV at materially lower vol across ≥2 universes, and D-Wave beats SA on
  the maxdiv selection at 40–60 assets.

### A2. Shrinkage / equal weights (the weights step over-fits)
- **Finding** (§5): **equal-weighting the *same* selection beats MV `optimal_weights` in 5–6/8
  windows** — the μ-driven weight QP adds estimation noise OOS (classic DeMiguel "1/N").
- **Prototype:** in `financial.weighting`, add (a) **Ledoit–Wolf Σ shrinkage** before the QP, and/or
  (b) an **equal-weight** option. Make it a config knob; keep the convex QP as default.
- **Test:** the OOS backtest already includes an EqualWeight method — add a shrinkage method and
  compare Sharpe/vol/win-rate.

---

## Direction B — increasing the asset universe (scale)

**Results** (§8, §9, and the SA-escalation / Gurobi-scaling run):
- The **select encoding is N binary vars**, so the **D-Wave clique sampler embeds to 80 assets**
  (chain-breaks ≤2.5%, ~60–75 ms QPU) — **~4× the old bit-encoding's ~18–20 limit.**
- **D-Wave beats SA at 40 and 60 assets** (β on) by 3–4%; the edge degrades by 80. **Sweet spot
  ≈40–60.**
- **SA is in a *genuine* local minimum** there: 100× reads and 20× sweeps don't move the gap, and it
  collapses to **1 unique portfolio** across the reads — only the QPU escapes (§ SA escalation).
- **Gurobi (exact) breaks at ~60**: optimal to 40 (proven, 0.1 s); at 60 it hits the 30 s limit with
  a **26.6% MIP gap** (NP-hard cardinality + nonconvex β). So at 60+ there is **no tractable exact
  oracle** — exactly where heuristics + the QPU matter.
- β's OOS benefit **scales with N**: marginal ≤30 (the booth's 28 universe), clearly helps 40–60.

**Booth implication:** the 28-asset universe sits *just below* the sweet spot. Expanding toward
**40–60 assets makes both the portfolios better OOS and the quantum win genuine.** This is the
highest-leverage product direction.

**To push further:**
- Build a **~150-name Yahoo universe** and push the QPU to **100–120** to find the hard embed/quality
  wall (Pegasus max clique ≈177). Today's runs were universe-limited (≈71–92 liquid names).
- For each N: SA vs D-Wave vs Gurobi via `scripts/qtw_scale_qpu.py`; report gap **to best-of-all** (NOT
  to Gurobi — Gurobi isn't optimal ≥60).

---

## Open questions / prioritized next steps
1. **Prototype MaxDiv (A1)** + validate on a winsorized multi-universe backtest + a bounded QPU run.
2. **Shrinkage/equal weights (A2)** — likely a free OOS win.
3. **Scale the universe to 100–120** (Direction B) — find the QPU wall; concretize the 40–60 demo.
4. Decide whether to **delete the penalized encoding** (superseded; dead weight).
5. (Ops, unrelated to research) rotate + delete `dwave-key.txt` / `test_DELETE.txt`.
