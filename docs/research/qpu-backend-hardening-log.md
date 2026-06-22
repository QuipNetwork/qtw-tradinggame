# Backend hardening loop — log (branch: backend-hardening)

Autonomous /loop. Each iteration: hypothesis → research → action → result. Tests stay green
(backend pytest + ruff) at every step. Code+tests committed to backend-hardening; this log is
untracked scratch. Pillars rotated: FORMULATION · CODE QUALITY · SECURITY · ROBUSTNESS.

## Iter 1 — 2026-06-22 — FORMULATION/ROBUSTNESS: optimal_weights feasibility guard
- Hypothesis: optimal_weights returned `res.x` unconditionally; a non-converged SLSQP solve
  (ill-conditioned/near-singular Σ) could silently return budget/box-violating weights, which the
  router's feasibility gate then drops — the solver loses for a non-quality reason.
- Research: SLSQP may return success=False (ftol not met) yet a usable point; a truly failed solve
  can return infeasible x. Prior sweep saw 0 failures on real+synthetic → LATENT gap, not live bug.
- Action: gate on ACTUAL feasibility (Σw=1 + box), not res.success; on violation fall back to equal
  weight 1/k (guaranteed feasible since K·w_min ≤ 1 ≤ K·w_max). New tests/test_weighting.py covers
  the feasibility contract (random, near-singular Σ, tight box = forced equal weight, empty support).
- Result: 137 pass (+8), ruff clean. Committed.

## Iter 2 — 2026-06-22 — CODE QUALITY: DRY the β-coupling (drift-proof, vectorized)
- Hypothesis: the β diversification coupling was duplicated as two near-identical O(N²) Python
  loops in encode_select and encode_method3 (yidx is identity, so both write the same 0.5·β·ρ to
  the top-left N×N block). CLAUDE.md flags exactly this "edit one, miss the other" drift hazard.
- Action: extracted `_add_frustration_coupling(Q, rho, beta, n)` — one vectorized in-place helper
  (`Q[:n,:n] += 0.5·β·ρ` with zeroed diagonal); both encoders now call it. Removes ~14 duplicated
  lines and the two Python loops; the β convention now lives in ONE place.
- Result: behavior preserved (test_encode_select_beta_adds_correlation_coupling and
  test_frustration_beta_rewards_diversification assert the exact β·ρ pair coefficient). 137 pass,
  ruff clean. Committed.

## Iter 3 — 2026-06-22 — SECURITY: bound API request inputs (resource-exhaustion guard)
- Hypothesis: user-facing request schemas (AgentConfig create, OptimizeRequest) had UNBOUNDED
  string/list fields — name/handle/email/update_frequency strings, reach_out/assets lists, and
  hold_count had no upper bound. An oversized payload (huge assets list, megabyte name, or huge
  unknown-ticker list) reaches validate_basket (which builds a giant `unknown` error string) and
  persistence → memory/storage DoS surface. Sliders/tickers ARE otherwise whitelisted+clamped.
- Action: add pydantic bounds at the boundary — name≤80, handle≤40, email≤254, update_frequency≤16,
  reach_out≤20 items, assets≤64 items with per-item _Ticker≤12 chars (universe tickers are ≤6),
  hold_count le=100. Oversized input now 422s before touching validate_basket/persistence.
  AgentUpdate left alone (server→client, not a request). New tests/test_schemas.py.
- Result: 140 pass (+3), ruff clean. Committed.

## Iter 4 — 2026-06-22 — CODE QUALITY/ALTITUDE: decouple SA from the D-Wave provider
- Hypothesis (after refuting an API-error-mapping concern — routes already map KeyError→404,
  ValueError→422, QpuBudgetExceeded→429, SolverFailed→503 correctly): the CPU solver sa.py imported
  reads_for_vars from the D-Wave provider module — a wrong-direction CPU→QPU coupling (a lean
  CPU-only deploy, or any future Ocean-at-import in dwave.py, would drag the QPU module into SA).
- Action: moved reads_for_vars (a pure config.DWAVE_READS_BY_VARS lookup) to the neutral
  solvers/sampling.py; sa.py and dwave.py both import it from there; srt_for_vars stays D-Wave-only.
  Updated test_dwave import.
- Result: importing backend.solvers.providers.sa in a fresh process no longer pulls in the dwave
  provider (verified: False). 140 pass, ruff clean. Committed.

## Iter 5 — 2026-06-22 — FORMULATION (negative) + SECURITY (verify+guard)
- (a) FORMULATION — tested exact-best-K-of-pool vs greedy projection (free, SA reads, rugged
  instances). RESULT: NOT a clear win → not implemented. Decisive finding: the penalty-free select
  QUBO's low-energy reads turn on VERY FEW assets — the union/pool across 500 reads is only 4–7 even
  at K=8–12 (pool < K). So exact-of-pool is inapplicable at high K (can't choose K from <K), and at
  low K greedy already equals exact (prior diagnostic). The greedy ADD-from-all-N loop does most of
  the selection; the sampler surfaces a small core. Mechanistic explanation for high-K SA-favored
  ties: the QUBO barely selects → greedy finishes classically → SA and D-Wave converge.
  DEFERRED hypothesis: for K>N/2, encode the COMPLEMENT (which N−K to DROP) — smaller selection,
  possibly better sampler behaviour. Non-trivial; needs its own experiment.
- (b) SECURITY — audited secret handling. CLEAN: no secret VALUE is ever logged/printed/interpolated;
  DATABASE_URL only feeds create_engine (SQLAlchemy masks the password in reprs/errors); the one
  f-string DDL (_ensure_columns) uses hardcoded constants only (no user input → no injection);
  /healthz exposes booleans/enums (persistence, qpu_configured), not the URL/token. Added
  tests/test_health_secrets.py to LOCK this in (regression guard). 142 pass, ruff clean. Committed.

## Iter 6 — 2026-06-22 — ROBUSTNESS: assets-api failure handling (hot-path dependency)
- Hypothesis: the optimize hot path depends on the remote assets-api. Audit found it mostly solid
  (HTTP timeout set, retries+backoff, HTTPStatusError→AssetsApiError, bad closes→NaN, spot stale
  fallback) BUT two gaps: (1) `body.get("bars", {})` returns None when the payload is `"bars": null`
  → `.get` on None = unhandled AttributeError (500); same for `"prices": null`. (2) AssetsApiError
  is a RuntimeError, NOT caught by the optimize route → market-data outage returns 500, not 503,
  and str(exc) would leak the internal assets-api URL/path.
- Action: (1) `body.get("bars") or {}` / `body.get("prices") or {}` → null payloads degrade to a
  clean AssetsApiError. (2) route maps AssetsApiError → 503 with a GENERIC detail ("market data
  temporarily unavailable") so the internal URL/path isn't leaked. Tests: null-payload→AssetsApiError
  (x2), optimize→503 with no path leak.
- Result: 145 pass (+3), ruff clean. Committed.

## Iter 7 — 2026-06-22 — FORMULATION (negative) + CODE QUALITY (DRY)
- (a) FORMULATION — tested the deferred select-COMPLEMENT encoding (select which N−K to DROP, hold
  the complement) at high K (15a/K11, 18a/K12/K14, 24a/K18, 28a/K20). RESULT: DROP is IDENTICAL to
  HOLD at every instance — both already reach the Gurobi optimum (0.00% gap). At high K the selection
  is easy (greedy-add nails it even from a small pool), so the complement buys nothing. NOT
  implemented. Conclusion across iter5+iter7: the C2 greedy projection is robust across the whole
  K-spectrum (optimal at low and high K); the only residual gap is MID-K rugged instances (e.g.
  18a/K9 ~7%) — which is precisely the QPU's value-add (D-Wave beats SA there). The formulation is
  sound; the lever for the mid-K gap is the SAMPLER, not the encoding/projection.
- (b) CODE QUALITY — `_select_solution_c2`'s per-support cache-fill re-implemented `select_weights`
  (greedy-project → optimal_weights → scatter into N-vector). Extracted `weights_for_support(support,
  problem)`; both `select_weights` and the live-race cache call it. Removes the duplicated QP-scatter
  and a divergence risk; sampling.py drops its direct optimal_weights import.
- Result: 145 pass (behavior preserved by existing C2 + verify-dwave tests), ruff clean. Committed.

## Iter 8 — 2026-06-22 — ROBUSTNESS: fault-isolate the race against any provider crash
- Hypothesis: race() caught only SolverFailed from future.result(). A provider raising ANY OTHER
  exception (D-Wave network drop, numpy LinAlgError, a bug) propagates out of the loop and the `try`
  (which only catches TimeoutError) → the WHOLE race dies and the other solvers' results are lost.
  A race exists for redundancy; one solver's crash must not sink it. (The empty-feasible/all-fail
  path was already clean: pick_winner→None → SolverFailed → 503.)
- Action: broaden the per-future catch SolverFailed→Exception (noqa BLE001, intentional) — any
  single-provider failure is recorded as a "failed" SolverRun (error string kept for audit) and
  skipped; the rest of the race still produces a winner. All-fail → empty feasible → SolverFailed.
  Tests: (1) one provider RuntimeError → healthy solver still wins, crasher recorded failed;
  (2) every provider crashes → SolverFailed.
- Result: 147 pass (+2), ruff clean. Committed.

## Iter 9 — 2026-06-22 — SECURITY/ROBUSTNESS audit (solid) + EventBus contract tests
- Audited the concurrency/robustness-sensitive paths flagged as candidates; all verified SOUND, no
  fix warranted (forcing one would be churn):
  - QPU budget: reserve() is atomic (RLock, prune→check→append) → no in-process TOCTOU even though
    optimize runs in threads. (Multi-WORKER TOCTOU exists but is low-severity for a soft quota +
    single-process booth + needs DB-level atomicity — out of scope, noted.)
  - Budget ACCOUNTING (job.py): reserve() runs right before race(); a failed race still counts the
    admission — correct, since include_qpu means the QPU actually ran. Pre-check is an early reject.
  - EventBus: publish snapshots subscribers to a tuple + drops on QueueFull (slow-consumer safe);
    all publish/subscribe happen on the loop (optimize publishes after to_thread returns).
  - WS _pump: unsubscribes in a `finally` → no subscriber leak on disconnect.
- DELIVERABLE: the EventBus core behaviors (drop-on-full, unsubscribe cleanup, no-op publish) were
  only tested transitively (via the gurobi-gated WS test). Added tests/test_event_bus.py to lock in
  the contract — esp. drop-on-full, the property that keeps a stuck WS from blocking the booth.
- Result: 153 pass (+6), ruff clean. Committed.

## Iter 10 — 2026-06-22 — ROBUSTNESS: lock in the slider_map feasibility invariant
- Hypothesis: the whole solve (and iter1's optimal_weights equal-weight fallback) assumes a FEASIBLE
  box — for effective cardinality c, c·w_min ≤ 1 ≤ c·w_max. Does slider_map guarantee it across the
  WHOLE slider × basket-size × K space, or can some combo produce an infeasible box?
- Analysis: it holds. method3: w_max ≥ grid_min_cap = ⌈M/K⌉/M ⇒ K·w_max ≥ 1; w_min = u_min/M with
  METHOD3_U_MIN=1 and M ≥ K ⇒ K·w_min = K/M ≤ 1. convex: w_max ≥ 1/n ⇒ n·w_max ≥ 1; w_min =
  0.25/n ⇒ n·w_min = 0.25 ≤ 1. Existing tests only covered a few specific cases.
- Action: added a parametrized property test sweeping every basket size (3..28) × box-affecting
  sliders × K∈{None,3,n/2,n}, both modes, asserting w_min≤w_max, c·w_min≤1≤c·w_max, M≥K,
  K∈[3,min(n,32)]. No bug found — but this LOCKS the invariant so a future config/grid change that
  breaks feasibility fails loudly (it underpins optimal_weights + the QP).
- Result: 155 pass (+2), ruff clean. Committed.

## Iter 11 — 2026-06-22 — ROBUSTNESS: deadline propagation (verified) + MTM per-agent isolation
- (a) Deadline propagation — VERIFIED sound: gurobi.solve_qp sets TimeLimit=deadline_s (+ NonConvex=2
  for β-MIQPs), so Gurobi is bounded; SA doesn't honor the deadline but is fast at booth scale
  (<1s for ≤28-asset QUBOs, well under RACE_OVERALL_DEADLINE_S). No fix.
- (b) MTM loop — FOUND + FIXED: run_mtm_loop tick-isolated the common failure (spot fetch) but the
  per-agent body sat inside that ONE broad try. A single agent's failure (e.g. a DB write) skipped
  the rest of the tick, and a PERSISTENTLY-bad agent permanently starved every agent ordered after
  it → stale P&L on the live feed. Same fault-isolation principle as iter8's race fix.
- Action: wrapped the per-agent body in its own try/except (rate-limited warn + skip that agent);
  the outer try still handles spot-fetch/tick-level failures. Test: with a store that raises on one
  agent's set_valuation, the healthy agent (ordered after it) is still revalued and published.
- Result: 156 pass (+1), ruff clean. Committed.

## Iter 12 — 2026-06-22 — ROBUSTNESS/CONSISTENCY: DbAgentStore orphan on DB write failure
- Hypothesis: DbAgentStore.create catches only IntegrityError (id collision → pop in-memory record
  + retry). If the DB insert fails for ANY OTHER reason (DB down → OperationalError), it's uncaught,
  so super().create's in-memory record stays in the hot path UNPERSISTED — a write-through
  inconsistency: the agent exists in memory (get/leaderboard see it) but not in the DB, and the
  client got a 500 with no id. On restart it vanishes.
- Action: added `except Exception` (after IntegrityError) that pops the in-memory record and
  RE-RAISES (no pointless retry on a down DB) — so any DB write failure leaves the hot path
  consistent with the DB. Test: a stubbed engine that raises on begin() → create() raises and
  store._agents is empty (no orphan).
- Result: 157 pass (+1), ruff clean. Committed.

## Iter 13 — 2026-06-22 — ROBUSTNESS verify (pnl) + div-by-zero regression tests
- Audited pnl.mark_to_market (live MTM hot path). SOLID: both division sites are already guarded
  (`if total else 0.0` for holding pct, `if bankroll_usd else 0.0` for pl_pct); missing-ticker is a
  documented precondition the MTM loop guarantees (union snapshot), now also isolated per-agent
  (iter11). No fix.
- DELIVERABLE: test_pnl.py covered normal/stale cases but NOT the zero-edge guards. Added a test
  (zero total via 0 spot price; zero bankroll) locking in both div-by-zero protections on the live
  path.
- Result: 158 pass (+1), ruff clean. Committed.

## Iter 14 — 2026-06-22 — FINAL: decoder/feasibility verified solid → hardening pass COMPLETE
- Audited the last core paths. SOLID, no fix: qubo_decoder.decode_bitstring normalize is guarded
  (`if total > 0 and |total-1|<=TOL`); convex w_min>0 so an all-zero sample sums >0; method3 divides
  by M≥8. check_feasibility has no division, never reduces an empty array (N≥3 guaranteed), and the
  all-zero method3 case is guarded (`if held.any() else 0.0`). 2nd consecutive no-bug iteration →
  declaring the pass complete (skip optional-coverage churn).

# ───────────────── CLOSING SUMMARY — backend hardening pass ─────────────────
Branch `backend-hardening` (from baseline 76c12ae). 158 tests (+29 since baseline), ruff clean on
every file the pass touched. 13 commits:

REAL FIXES (9):
- optimal_weights always returns a feasible portfolio (guard + equal-weight fallback)
- API request input bounds (resource-exhaustion guard at the schema boundary)
- SA decoupled from the D-Wave provider (reads_for_vars → neutral sampling module)
- assets-api failure handling (null payloads → clean error; outage → 503, no internal-URL leak)
- race fault-isolation (ANY single-provider crash recorded+skipped, not fatal)
- MTM loop per-agent fault-isolation (a bad agent can't permanently starve the live feed)
- DbAgentStore: no unpersisted in-memory orphan when a DB write fails
- β-coupling DRY'd into one vectorized helper (drift-proof)
- chosen-support→weights DRY'd into weights_for_support

VERIFIED-SOLID + REGRESSION TESTS (4): secret handling (/healthz leak test), EventBus contract
(drop-on-full), slider_map feasibility invariant (full-space), pnl div-by-zero guards.

FORMULATION NEGATIVES (rigorously ruled out, prevented bad complexity): exact-best-K-of-pool
projection (greedy already optimal; pool<K at high K); select-COMPLEMENT encoding (DROP ≡ HOLD,
both optimal at high K). The C2 greedy projection is robust across the K-spectrum; the only residual
gap is MID-K rugged instances — which is the QPU's value-add (D-Wave beats SA there).

DEFERRED (need their own session, not churn):
- select-complement at MID K (only high-K was tested; mid-K is where ruggedness lives)
- multi-WORKER QPU-budget TOCTOU (per-process lock is fine single-process; multi-uvicorn needs
  DB-level atomicity — out of scope for the single-process booth)
- optimal_weights res.success deep-dive (latent; current feasibility-gate fallback covers it)

NOTES FOR REVIEW:
- The branch also carries 4 FRONTEND-polish commits (dd540b3, c78f178, 672f9c5, 79fbe81) from a
  PARALLEL /loop that shared this git checkout — they sit between the baseline and the backend work
  (clean linear history, disjoint files: mvp/ vs backend/). Merging backend-hardening brings both.
- 3 backend files have PRE-EXISTING ruff-format drift NOT from this pass (pnl.py, notifications/
  email.py, persistence/qpu_budget.py) — left untouched to avoid scope-creep; `ruff format` them
  separately if wanted.
