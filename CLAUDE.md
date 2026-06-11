# CLAUDE.md — Project context

Context for working on this repo. Kept current — if something here contradicts
the code, the code wins; fix this file.

## 1. Project

**Quip Network · QTW 2026 Trading Competition** — booth activation for Quantum
Tech World 2026 (Jun 25–26). Attendees pick a basket of assets at a kiosk, tune
3 strategy sliders, get a $10K virtual bankroll, and watch their portfolio
compete live. Every (re)optimization races solvers — SA (CPU) vs D-Wave
Advantage (QPU), with Gurobi in dev — and the winner's provenance becomes a
badge on every screen.

- Repo: gitlab.com/quip.network/qtw-tradinggame · Preview: https://qtw-tradinggame.netlify.app
- Companion service: gitlab.com/quip.network/assets-api (price indexing, REST)
- Status & next steps: [TODO.md](TODO.md) · Dataflow: [docs/BACKEND_DAG.md](docs/BACKEND_DAG.md)

## 2. Layout

```
mvp/                  Vite + React frontend (kiosk, phone, TV). Runs on mocks
                      until wired: UI imports only mvp/src/api/index.ts.
backend/              Python backend (FastAPI). See backend/README.md to run/test.
shared-design/        Shared CSS, asset icons, glyph/QR canvas code.
design-doc.html       Frontend design source of truth (renders the mock screens).
docs/BACKEND_DAG.md   System dataflow (Mermaid + prose).
```

## 3. The model (current)

A continuous **box-constrained QP** over the player's selected basket:

```
min  (γ/2)wᵀΣw − μᵀw + λ_t‖w − w_ref‖²
s.t. Σwᵢ = 1;  w_min ≤ wᵢ ≤ w_max
```

| Control | Parameter | Meaning |
|---|---|---|
| Risk Preference | γ | Variance penalty (inverted, log-scaled). No lookback effect. |
| Max Position Size | w_max | Cap relative to basket: 1/n → 50%. |
| Rebalance Frequency | schedule only | Scheduled re-opt cadence, tiers 24/8/4/2/1h. Not in the objective. |
| Asset grid | basket n | Human picks ≥3 of the 25-asset universe. Replaces the old K slider. |
| Min position | w_min = 0.25/n | Participation floor, not user-facing. |
| Return lookback | τ = 168h | Feeds μ. Fixed config. |
| Risk lookback | T = 720h | Feeds Σ. Fixed config (extendable to 2160h). |

**Turnover**: first solve λ_t = 0 (nothing to anchor to); retune anchors to the
drifted held weights with λ_t = `TURNOVER_PENALTY_MULT × γ × mean(diag Σ)`.
**No transaction fee — ever.** Trade pressure is rate limiting (per-user manual
retune cooldown, the rebalance cadence, a global QPU token bucket — see TODO).
There is **no cardinality constraint**: the basket *is* the discrete choice.

## 4. Solver race

The QP goes to Gurobi natively; SA and D-Wave get a bit-discretized QUBO
(`b=4` bits per asset over [w_min, w_max], single budget penalty). First
**feasible** result wins (budget + box check); decoded QUBO weights are
simplex-normalized to absorb bit-grid error, and samplers pick the best
feasible read, not the lowest energy.

- D-Wave joins only when `DWAVE_API_TOKEN` is set; uses the clique sampler
  (cached embeddings); reports QPU access time.
- `GUROBI_IN_RACE = False` for production — Gurobi is dev/oracle only
  (licensing). The live race is SA vs QPU.

## 5. Market data

`MarketDataSource` protocol with two implementations, chosen by the
`MARKET_DATA_SOURCE` env var:

- **assets-api** (default) — the companion Go service: hourly OHLCV + spot for
  all 25 assets over REST, SQLite-backed, provider routing (Alpaca → Massive →
  CoinGecko). Backend forward-fills stock market-hour gaps onto the hourly grid.
- **synthetic** — deterministic seeded stand-in; used by tests and offline demos.

The 25-asset universe (14 crypto + 11 stocks) lives in
`backend/src/backend/financial/basket.py` and must stay in sync with
assets-api's `assets.yaml` and the frontend's `mvp/src/api/assets.ts`.
(2026-06-10 swaps: QNT→HON, SPCX→GOOGL, BTQ→IBM.)

## 6. Runtime shape

- One optimize request: basket → slider_map → μ/Σ from history → race → weights
  → trades → holdings persisted as **token units** → `RoutingResult`.
- MTM loop (~3s): one batched spot snapshot → every agent's units × spot →
  `AgentUpdate` pushed over `WS /agents/{id}`; leaderboard is derived on read.
- TV: `GET /leaderboard` for rankings; `WS /tv/events` for new-agent splashes.
- Persistence is in-memory (single worker); SQLite planned for booth durability.

## 7. Conventions

- Python attrs snake_case, JSON wire camelCase (pydantic aliases) — mirrors
  `mvp/src/api/types.ts`, the contract source of truth.
- Math-notation identifiers (γ→gamma, Σ→Sigma, N, Q…) are deliberate; ruff's
  naming rules for them are disabled in `backend/pyproject.toml`.
- No `uv` on this machine — use `backend/.venv` (python3.12). Tests:
  `.venv/bin/python -m pytest -q`. CLI: `.venv/bin/qtw market|optimize|race`.
- Comments: restrained — only non-obvious constraints; no narration.
