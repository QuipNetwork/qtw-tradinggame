# CLAUDE.md — Session context

Context for resuming the backend implementation work. This file captures everything an incoming session needs to pick up without re-touring the codebase.

---

## 1. Project

**Quip Network · QTW 2026 Trading Competition** — booth activation for Quantum Tech World 2026 (Jun 25–26, 2026).

Attendees create a trading agent at a kiosk, tune 5 strategy sliders, get a $10K virtual bankroll, and watch their portfolio compete in real time. Every retune is routed through the Quip Network across D-Wave Advantage (QPU), Simulated Annealing, and Gurobi — the first feasible solution wins, and the "solved by" provenance is surfaced as a badge on every UI.

- Repo: gitlab.com/quip.network/qtw-tradinggame
- Live preview: https://qtw-tradinggame.netlify.app
- Source of truth: `design-doc.html` (2,718 lines, 12 sections at repo root)

**Current state: frontend MVP only.** No backend is built. The MVP is a complete contract surface (TypeScript types + mocked impl) ready to swap in a real backend.

---

## 2. Repo layout

```
design-doc.html              Full project summary — 12 sections, source of truth
IMPLEMENTATION_NOTES.txt     V0 scope notes — what's deferred and why
BACKEND_DAG.md               System DAG (Mermaid) — all components and dataflow
mvp/                         Vite + React 18 + TypeScript SPA (the live MVP)
  src/
    main.tsx                 Boot. Injects shared SVG symbols into <body>.
    App.tsx                  Router: /, /kiosk, /kiosk/welcome, /p/:agentId, /tv
    api/
      types.ts               8 contract types (see §4)
      mocks.ts               localStorage + setInterval impl
      index.ts               Single re-export point — UI imports only this
    routes/
      Index.tsx              Preview hub for all surfaces
      Kiosk/SignUp.tsx       Name + handle + 5 sliders → submitAgent → optimize
      Kiosk/Welcome.tsx      Post-launch confirmation, portfolio, QR, glyph
      Phone/Profile.tsx      Live P&L + retune sliders
      TV/BoothTV.tsx         Rotator: A(12s)→B(15s)→C(20s); D forced via ?state=D
      TV/StateA.tsx          Top-10 leaderboard
      TV/StateB.tsx          Per-rank spotlight
      TV/StateC.tsx          Welcome/intro splash
      TV/StateD.tsx          New-agent welcome splash
    utils/
      glyph.ts               Typed wrapper around @shared/glyph.js
      strategy.ts            Slider → weights PLACEHOLDER formula (see §8.2)
  vite.config.ts             Aliases @shared → ../shared-design
shared-design/
  glyph.js                   Deterministic canvas primitives
  v4-mocks.css               5,312 lines of shared styling
  symbols.svg.html           SVG <symbol> library — Quip wordmark, crypto glyphs
reference-files/             Base @ Consensys Miami screenshots
netlify.toml                 Auto-deploys mvp/ on every push
```

---

## 3. Backend architecture (proposed, unbuilt)

```
backend/
├── api/                     HTTP/WS surface — matches mvp/src/api/types.ts
│   ├── routes.py            POST /agents, GET /agents/{id}, POST /agents/{id}/optimize, ...
│   ├── schemas.py           Pydantic mirrors of AgentConfig, RoutingResult, etc.
│   ├── ws.py                subscribeAgent push channel (SSE or WebSocket)
│   └── leaderboard.py       GET /leaderboard
├── financial/               Domain-aware — assets, prices, semantics
│   ├── basket.py            15 tickers + chain/decimals metadata
│   ├── prices/oracle.py     Live spot for mark-to-market
│   ├── prices/history.py    Hourly OHLCV cache for Σ/μ
│   ├── estimators/covariance.py     Σ on 30-day hourly window, cached
│   ├── estimators/expected_return.py μ from user's τ-window hourly returns
│   ├── slider_map.py        SliderValues → (γ, w_max, τ, K, λ_t) — SINGLE SOURCE OF TRUTH
│   ├── qubo_encoder.py      (μ, Σ, params, w_prev) → QuboMatrix + DecodeMeta
│   ├── qubo_decoder.py      bitstring + DecodeMeta → weights → PortfolioEntry[]
│   ├── retune.py            Diff old→new weights, compute trade list, optional fee
│   └── pnl.py               holdings × live prices → AgentUpdate
├── solvers/                 Solver-routing layer — sees only Q
│   ├── router.py            Dispatch in parallel, first-feasible wins
│   ├── feasibility.py       Constraint validator (budget, box, cardinality) — V0 quality bar
│   ├── providers/{base,dwave,sa,gurobi}.py
│   └── types.py             QuboMatrix, Solution, ProviderProvenance
├── orchestration/
│   ├── job.py               End-to-end pipeline
│   ├── scheduler.py         Σ refresh, leaderboard MTM tick, oracle health
│   └── deadlines.py         Per-job time budgets
├── persistence/
│   ├── agents.py            AgentConfig + current holdings + retune history
│   ├── jobs.py              Audit log per Q hash
│   └── leaderboard.py       Rank by total = bankroll + MTM P&L
├── events/
│   ├── bus.py               Pub/sub for TV (new-agent splash, rank reshuffles)
│   └── feeds.py             Per-channel fan-out
└── config.py                τ ranges, K bounds, bit precision, ε tolerance, bankroll
```

---

## 4. API contract — current TypeScript (`mvp/src/api/types.ts`)

| Type | Fields |
|---|---|
| `SliderValues` | `tradingActivity, riskPreference, tradeSize, holdingStyle, diversification` — all `number 0–100` |
| `AgentConfig` | `name`, `handle?`, `sliders: SliderValues` |
| `ProviderType` | `'QPU' \| 'CPU'` — **binary** (Gurobi + SA share the CPU label) |
| `AssetTicker` | `'BTC' \| 'ETH' \| 'SOL' \| 'USDC'` — **only 4** (backend spec says N=15) |
| `PortfolioEntry` | `ticker, pct, usd` — `pct` is the weight `wᵢ × 100` (sums to 100 across K nonzero entries) |
| `RoutingResult` | `provider: string, providerType, solveTime, vsClassical, portfolio[]` |
| `LeaderboardEntry` | `rank, agentId, name, handle, total, plUSD, plPct, jobsSolved, primaryProvider` |
| `AgentUpdate` | `plUSD, plPct, total` — `plUSD = total − bankroll`, `plPct = plUSD/bankroll × 100` |

**Five API functions** (mocked in `mvp/src/api/mocks.ts`):

| Function | Implied route |
|---|---|
| `submitAgent(config)` → `{agentId, qrUrl}` | `POST /agents` |
| `getAgent(id)` → `AgentConfig \| null` | `GET /agents/{id}` |
| `requestOptimization(id)` → `RoutingResult` | `POST /agents/{id}/optimize` |
| `getLeaderboard()` → `LeaderboardEntry[]` | `GET /leaderboard` |
| `subscribeAgent(id, cb)` → unsubscribe | `ws.py` SSE/WS |

**Mock behavior worth noting:**
- `mocks.ts` uses `localStorage` (per-browser only) and a static `TOP_10` array.
- 10 seeded demo agents `a01..a10` (Hilbert Spaceship, Bra-Ket Boy, …) work via deep links.
- `requestOptimization` randomly picks QPU 80% / CPU 20% with hand-tuned solve times.
- `subscribeAgent` does `setInterval(3s)` with random walk + upward bias.

---

## 5. Optimization spec

### 5.1 Objective — Mean-Variance

```
min_w   (γ/2)·wᵀΣw  −  μᵀw  +  λ_t·‖w − w_ref‖²
s.t.    Σwᵢ = 1                      (budget — invest all of it)
        0 ≤ wᵢ ≤ w_max               (long-only, per-asset cap)
        |{i : wᵢ > 0}| = K           (cardinality, exactly-K)
```

**Reference vector:**
```
w_ref = 0          on first solve (decision Q2 — unpenalized)
w_ref = w_prev     on retune (squared L2, stays quadratic for QUBO)
```

**Why mean-variance over Max-Sharpe**: Max-Sharpe (via Charnes-Cooper) is a feasible QP, but it has no `γ` for the user to manipulate. Mean-variance gives the Risk Preference slider a direct knob on the objective. Without that knob the slider has no economic meaning.

**Variable decomposition** — the decision variable is `w` (portfolio weight vector). Everything else (`Σ`, `μ`, `γ`, `λ_t`, `w_max`, `K`, `w_ref`) is data assembled before solve. The risk term `(γ/2)wᵀΣw` correctly credits diversification through Σ's off-diagonals. The penalty term `λ_t‖w − w_ref‖²` plays two roles depending on what `w_ref` is — anchoring to zero on first solve (effectively unpenalized in V0 since `λ_t = 0`), anchoring to current holdings on retune (a real turnover discouragement).

### 5.2 What type of program is this?

- **Without cardinality**: it's a **QP** — quadratic objective, linear constraints (budget + box).
- **With cardinality (exactly-K)**: it's **MIQP** (Mixed-Integer Quadratic Program). Add binary `yᵢ ∈ {0,1}` indicators, constraint `Σyᵢ = K`, coupling `wᵢ ≤ w_max·yᵢ`. **This is Gurobi's native input form** — feed it MIQP, get back optimal `w` directly.
- **For D-Wave / SA**: convert MIQP → **QUBO** via bit discretization (see §5.6). All decision variables become binary.

The race sends the **same problem** to all three solvers, just in two encodings (MIQP for Gurobi, QUBO for D-Wave/SA).

### 5.3 Return and covariance estimation

Hourly log-or-simple returns:
```
r_{i,t} = P_{i,t} / P_{i,t-1} − 1
```

`t` is the time index over the estimation window. Hourly granularity.

Mean (per-asset, user's τ window):
```
μ_i = (1/τ) · Σ_{t=1}^{τ} r_{i,t}
```

Covariance (pairwise, fixed Σ window):
```
Σ_{ij} = (1/(T-1)) · Σ_{t=1}^{T} (r_{i,t} − r̄_i)(r_{j,t} − r̄_j)
```

**Two estimation windows — important distinction:**

| Window | Length | Source | Slider-controlled? |
|---|---|---|---|
| **Σ (risk)** | fixed 720 hourly observations (30 days × 24h) | `prices/history.py` cache | **No** — periodic refresh by scheduler |
| **μ (return)** | user's τ-window hourly returns | `prices/history.py` cache | **Yes** — via Holding Style slider |

τ is the only slider that changes input data. The other four sliders are just coefficients in the objective.

### 5.4 Slider → parameter mapping (`slider_map.py`) — single source of truth

| Slider | Param | Range | Effect |
|---|---|---|---|
| Risk Preference | `γ` | `[γ_min, γ_max]`, log-scaled (~0.5–20) | Variance weight vs return. Aggressive → low γ; conservative → high γ. |
| Trade Size | `w_max` | `[1/K, 1]` or fixed `[0.2, 0.8]` | Per-asset cap. Low → near-equal weights; high → concentration allowed. |
| Holding Style | `τ` | `[24, 720]` hours | μ lookback. Patient → long τ; restless → short τ. **Only slider that changes input data.** |
| Diversification | `K` | `{1, …, N}` integer (e.g. 3–12 for N=15) | Cardinality — number of nonzero positions. |
| Trading Activity | `λ_t` | `[0, λ_max]`, inverted (high slider = low λ_t) | Turnover penalty. **V0: λ_t = 0**. |

### 5.5 Mark-to-Market (MTM) loop

The **MTM loop** is the continuous revaluation cycle that runs in the background between retunes:

```
for each agent:
    new_value = Σᵢ (holdings_i × spot_price_i)
    plUSD = new_value − bankroll
    plPct = plUSD / bankroll × 100
    push AgentUpdate over WS
```

**MTM doesn't trade anything** — it only updates what the existing positions are worth right now. This is what makes the displayed P&L move even when the user does nothing. Drives the live ticker on Phone and TV.

The MTM loop only stops when the user retunes (which throws the agent back to the top of the build-and-solve pipeline with a freshly sampled μ).

### 5.6 QUBO encoding (for D-Wave / SA)

**Step 1 — discretize weights:**
```
wᵢ ≈ (w_max / (2^b − 1)) · Σ_{k=0}^{b−1} 2^k · xᵢₖ      xᵢₖ ∈ {0,1}
```
At `b = 4`: 16 levels per asset, ~6% granularity at `w_max = 0.5`. 15 assets × 4 bits = **60 binary vars** — fits Advantage with embedding headroom.

**Step 2 — constraints → quadratic penalties:**

| Constraint | Penalty term |
|---|---|
| Budget `Σwᵢ = 1` | `λ_sum · (Σwᵢ − 1)²` |
| Cardinality `Σyᵢ = K` | `λ_K · (Σyᵢ − K)²` where `yᵢ = 1 iff Σₖ xᵢₖ ≥ 1` (encoded via auxiliary penalties) |
| Box cap `wᵢ ≤ w_max` | Handled implicitly by bit encoding (max value = w_max) |

**Step 3 — penalty tuning:** `λ_sum, λ_K ≈ 10×` the largest |Σᵢⱼ| or |μᵢ| coefficient. Validate by running Gurobi (oracle) — if its solutions are infeasible at these penalties, raise them.

**Hyperparameters that require empirical sweeps** (plan a day before booth):

- **D-Wave**: chain strength (Ocean SDK auto-tune is fine for V0), annealing_time (default 20 μs, can extend to 100+), num_reads (start 1000), anneal_schedule (default fine).
- **SA** (via `dwave-neal`): cooling schedule (geometric), β-range, num_sweeps, num_reads. Use the same `neal` package for consistency in the race.

### 5.7 Solver race rules

- All three solvers (D-Wave, SA, Gurobi) get the **identical problem**. Gurobi gets MIQP; D-Wave/SA get QUBO encoded from it.
- **First feasible solution wins** (decision Q6 — feasibility-only quality bar for V0).
- Feasibility checks: `|Σwᵢ − 1| < ε_sum`, `0 ≤ wᵢ ≤ w_max + ε_box`, `|{wᵢ > 0}| = K`. Cheap, deterministic, no oracle in the hot path.
- Gurobi is the **offline oracle** — runs separately to validate parameter ranges and penalty weights. Not deployed live (licensing/IP).
- `vsClassical = winner_solve_time / runner_up_classical_solve_time` (decision Q7 — winner vs runner-up wall-clock).

---

## 6. Workflow

### 6.1 Build-and-solve (first half)

```
agent → slider_map → estimators(μ, Σ) → qubo_encoder → solvers.router (race) → qubo_decoder
                                                            ↓
                                              feasibility check + wall-clock
                                                            ↓
                                                first feasible wins
```

All three solvers receive the identical Q. The first to return a feasible solution takes the job. Gurobi serves offline as the oracle that calibrates penalty ranges.

### 6.2 Apply-and-track (second half)

The winning weight vector flows into a branch:

- **First solve** (`kind: 'first'`, no holdings): allocate bankroll by `w_new`.
- **Retune** (`kind: 'retune'`, has holdings): liquidate current holdings, rebuy at spot to match `w_new`. Value-neutral at the instant (minus fee in V1).

Both converge to persistence (store portfolio + winning provider badge), then the continuous **MTM loop** starts: live prices × held positions → `AgentUpdate` → leaderboard rank → WS push.

The MTM loop never touches the solver — pure holding until the user retunes, which restarts the build-and-solve pipeline with a freshly sampled μ.

---

## 7. Worked example — why path-dependence matters

**First solve, $10K bankroll, portfolio A:**

```
BTC 50% → $5,000   ETH 30% → $3,000   SOL 20% → $2,000
```

**6h later, prices move (BTC +4%, ETH +2%, SOL −1%), no retune:**

```
BTC $5,200  ETH $3,060  SOL $1,980   Total V = $10,240   P&L = +$240 (+2.4%)
```

Weights have **drifted** without a trade — BTC now 50.8%, ETH 29.9%, SOL 19.3%. This drifted vector is `w_prev` for the next retune.

**User retunes — shorter τ shifts μ toward LINK, away from SOL. Optimal portfolio B:**

```
BTC 30%   ETH 30%   LINK 40%   SOL 0%
```

**Trades to get from drifted-A to B on $10,240:**

```
BTC  50.8% → 30%   SELL $2,128
ETH  29.9% → 30%   BUY     $12
SOL  19.3% → 0%    SELL $1,980
LINK  0%   → 40%   BUY  $4,096
                   sells $4,108 = buys $4,108 ✓
```

One-way turnover = 40.1%. With `c = 0.3%`: fee = `0.003 × 0.401 × $10,240 = $12.32`.

Bankroll drops to $10,227.68. **You paid $12.32 to change your mind.**

If B's edge over drifted-A is only +$5 (as projected by μ), switching loses you $7.32. A frictionless model recommends the switch every time; a path-dependent one asks whether the improvement clears the cost of getting there. **This is what the `λ_t‖w − w_prev‖²` penalty inside the QUBO accomplishes** — and what makes the Trading Activity slider economically meaningful.

**Key economic point**: the QUBO penalty alone shapes the optimizer's choice but is **invisible to the user**. The explicit fee is what the user *sees* deducted from their bankroll. **Both must ship together in V1** — the penalty without the fee is "secret conservatism" with no economic feedback.

---

## 8. Gaps between current API and backend spec

### 8.1 Cross-cutting

1. **Asset basket unfrozen.** Type says 4 (`AssetTicker`); kiosk UI shows 6 (adds LINK, UNI in `SignUp.tsx`); backend spec says 15.
2. **First-solve vs retune is invisible at the API boundary.** Same call shape both times. No `kind`, `tradeList`, `fee` fields on `RoutingResult`.
3. **No slider-update endpoint.** `Profile.tsx#retune()` mutates local state and calls optimize but never persists updated sliders server-side.
4. **Provider provenance collapsed.** 3 backend solvers → 2 enum values. `ProviderProvenance` (Q hash, deadline, ε) lost.
5. **Bankroll is magic.** Hardcoded `BANKROLL = 10000` in `Kiosk/Welcome.tsx:8`. Not in API or config.
6. **MTM stream is rollup-only.** `AgentUpdate` is `{plUSD, plPct, total}`. No per-asset drift between retunes — kills the §7 visualization.
7. **TV event bus is timer-faked.** State D ("new agent → 10s splash") only reachable via `?state=D`. No real event subscription.
8. **No timestamps anywhere.** `RoutingResult`, `AgentUpdate` lack `solvedAt`/`asOf`. Stale data undetectable.
9. **`jobsSolved` lacks a source.** On `LeaderboardEntry` but nothing increments it.
10. **`vsClassical` semantics** — now resolved (winner vs runner-up wall-clock, Q7).

### 8.2 Footguns to fix when wiring real backend

- **`utils/strategy.ts::computeWeights` is misleading.** Looks like the slider→portfolio mapping but is a hand-tuned demo formula using only 3 of 5 sliders (`p3, p4` unused). `Kiosk/Welcome.tsx:66` uses it to render allocation instead of `result.portfolio` — so the welcome screen shows fake weights. Should be replaced with `result.portfolio` consumption.
- **`sessionStorage` handoff is device-local.** Kiosk caches `RoutingResult` under `quip:lastResult:<id>` (`SignUp.tsx:57`). Phone reads it (`Profile.tsx:33-35`). But phone is a different device — falls through to defaults. Real backend must persist the last result server-side.
- **`Profile.tsx#retune()` (line 71)** calls `requestOptimization(agentId)` without sending new sliders. Mock works because it returns random regardless.
- **`BoothTV.tsx:35`** calls `setSpotIndex` inside `setState`'s updater — React anti-pattern, will warn in StrictMode.
- **`StateA.tsx:3-12`** hardcodes a `CLASSICAL_BREAKDOWN` array summing to 12% (matches design-doc, not real telemetry).

---

## 9. Decisions

### 9.1 Resolved

| # | Question | Decision | Why |
|---|---|---|---|
| Q1 | Cardinality: exactly-K vs ≥K? | **Exactly-K** | Clean QUBO penalty `λ_K · (Σyᵢ − K)²` |
| Q2 | First-solve `w_ref` | **`0` (zero)**, not equal-weight | Avoids spurious bias toward `1/N` |
| Q3 | Transaction cost on retune? | **V0: none. V1: c ≈ 5–10 bps × turnover** | See §10 |
| Q4 | Bit precision per asset? | **b = 4** (16 levels) | Tune up to 5 if lumpy |
| Q5 | Penalty weights `λ_sum, λ_K`? | **~10× largest QUBO coefficient** | Validate via Gurobi infeasibility |
| Q6 | ε semantics | **Feasibility-only for V0** | Cheap, deterministic, no oracle in hot path |
| Q7 | `vsClassical` definition | **Winner solve_time / runner-up classical solve_time** | Honest "vs classical" framing |
| Q8 | Bankroll surfacing | **Server-side config**, returned by `submitAgent` and `getAgent` | One tunable per tournament; no frontend hardcoding |
| Q9 | Slider-update path | **Extend `requestOptimization` payload with optional `sliders?: SliderValues`** | Single round-trip, atomic. Alternative (PATCH then optimize) has race-condition risk |

### 9.2 Open

| # | Question | Notes |
|---|---|---|
| Q10 | Final asset basket (N=15 list)? | Use top-N by liquidity on CoinGecko. Lock before booth. |
| Q11 | Per-solver deadlines? | Likely 1–2s per solver; race overall ≤ 3s. Empirical. |
| Q12 | D-Wave embedding strategy? | Auto via Ocean SDK for V0; manual minor-miner tuning if chain-break rates > 5%. |
| Q13 | Concrete λ_max for Trading Activity slider in V1? | Empirical — pick value where slider extremes produce visibly different turnover. |

---

## 10. V0 explicit scope

What's **in** V0 (booth day):
- Full QP/MIQP/QUBO pipeline with mean-variance objective (no turnover penalty since λ_t = 0)
- 3-solver race (D-Wave + SA + Gurobi), first feasible wins
- Feasibility-only ε check
- First solve and retune (both re-allocate by `w_new`)
- Live MTM loop, leaderboard ranking
- 15-asset crypto basket via CoinGecko

What's **deliberately deferred** to V1:
- `λ_t > 0` turnover penalty in QUBO
- Explicit transaction fee `c · ½Σ|Δwᵢ| · V` deducted on retune
- Per-asset MTM drift in `AgentUpdate`
- Cached Gurobi reference for quality-bar ε checks
- TV event bus for State D (new-agent splash)

**Why V0 skips the penalty + fee pair**: as §7 explains, the QUBO penalty is "invisible economics" without the displayed fee. Shipping the penalty alone makes the optimizer secretly conservative for reasons the user can't see. Shipping the fee alone has nothing in the optimizer to weigh it against. They're a package — both in V1 together, neither in V0.

Details in [IMPLEMENTATION_NOTES.txt](IMPLEMENTATION_NOTES.txt).

---

## 11. Wiring plan (phased)

**Phase 0** — Backend skeleton. Create `backend/`, set up Python project, mirror `types.ts` as Pydantic schemas, stub modules.

**Phase 1** — Math core with synthetic data. Implement `slider_map`, `basket`, `estimators/*`, `qubo_encoder`, `qubo_decoder`. Plus solvers: Gurobi (MIQP) and SA (QUBO via `neal`). Unit tests use synthetic μ, Σ with known closed-form solutions.

**Phase 2** — Live market data. `prices/history.py` (CoinGecko hourly OHLCV cache) + `prices/oracle.py` (live spot). `pnl.py` for MTM.

**Phase 3** — API surface. `routes.py` (4 HTTP endpoints), `ws.py` (WS for `subscribeAgent`), `leaderboard.py`. Schemas mirror `types.ts`.

**Phase 4** — Persistence + orchestration. `persistence/{agents,jobs,leaderboard}.py`. `orchestration/{job,scheduler}.py` — end-to-end pipeline + Σ refresh + MTM tick.

**Phase 5** — D-Wave integration. `solvers/providers/dwave.py` via Ocean SDK. Empirical sweep on chain strength, annealing time, num_reads. Compare against Gurobi reference.

**Phase 6** — Events bus. `events/{bus,feeds}.py`. Wire State D in TV to real events.

**Phase 7** — Frontend wiring. Widen `types.ts` (basket=15, `kind`, `tradeList`, `fee`, `jobId`, timestamps). Create `api/real.ts`. Flip `api/index.ts`. Replace `computeWeights` usages with `result.portfolio`. Remove `sessionStorage` handoff. Fix `BoothTV.tsx` anti-pattern.

---

## 12. Pointers

- Design-doc sections relevant to backend work: **07** (slider→param mapping), **08** (architecture), **09** (API contract), **12** (open TBDs).
- The TypeScript contract is the authoritative shape. Pydantic schemas in `backend/api/schemas.py` mirror it.
- The single shared mapping `slider_map.py` is the only place 0–100 ↔ physical params live. Do not duplicate this on the frontend.
- `shared-design/glyph.js` is consumed by both `design-doc.html` (window.QuipGlyph) and the React app (`@shared` Vite alias). Visual changes there propagate to both.
- System DAG: [BACKEND_DAG.md](BACKEND_DAG.md).
- V0 scope notes: [IMPLEMENTATION_NOTES.txt](IMPLEMENTATION_NOTES.txt).
