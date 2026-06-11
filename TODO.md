# TODO

Backend for the QTW 2026 Trading Game. Core is built and tested (58 passing),
reconciled with the main-branch contract (3 sliders + 25-asset basket selection).
See `backend/README.md` to run and test, `docs/BACKEND_DAG.md` for the dataflow.

## Done

- **Contract v2** — 3 sliders (`rebalanceFrequency` discrete tiers / `riskPreference` / `maxPositionSize` relative to basket), 25-asset universe (14 crypto + 11 stocks, QNT included), per-agent basket (min 3 assets, fixed after sign-up), `email`/`reachOut`/`updatesOptIn` persisted.
- **Retune mechanics** — first solve: λ_t = 0 (nothing to anchor to); retune: λ_t‖w − w_prev‖² scaled to the data (`TURNOVER_PENALTY_MULT × γ × mean diag Σ`), so the held portfolio matters when moving to a new one. No transaction fee — ever; trade pressure is handled by rate limits instead. Participation floor 0.25/n; lookbacks fixed (μ 168h, Σ 720h).
- **Model** — cardinality dropped (basket expresses it): Gurobi solves a continuous QP; the QUBO has no indicator block; QUBO results are simplex-normalized, so **SA now genuinely competes** (feasible at all basket sizes).
- **D-Wave provider** — real Ocean-SDK implementation; token-gated entry into the race; QPU-access-time reporting; hermetic tests via sampler injection.
- **assets-api client** — `AssetsApiSource` implements `MarketDataSource` against `/v1/history` + `/v1/spot`, forward-filling stock market-hour gaps; flip `config.MARKET_DATA_SOURCE = "assets-api"` to use it.
- **API, persistence, orchestration, events, CLI** — as before, updated for the basket flow.

## Remaining (in order)

### 1. Run against real data
assets-api is now the default source (`MARKET_DATA_SOURCE=synthetic` to opt
out). Stand it up locally (Docker or `make run`), let the 90-day backfill
finish, and shake out real-data surprises (SAF via the SAFRY ADR, stablecoin
near-zero variance → consider Σ shrinkage). Basket is fully priceable after
the 2026-06-10 swaps (QNT→HON, SPCX→GOOGL, BTQ→IBM) — backend updated.

### 2. Frontend wiring
- `api/real.ts` (fetch + WS) + env-gate `api/index.ts` on `VITE_API_BASE` (mocks otherwise; Netlify preview unaffected).
- Local test loop: `uvicorn` on :8000 + `VITE_API_BASE=http://127.0.0.1:8000 npm run dev`.
- Welcome/Profile render `result.portfolio` from the server; drop the `sessionStorage` handoff; Profile sends sliders on retune; fix the `BoothTV` setState pattern.
- Mirror `MIN_BASKET_SIZE = 3` in the kiosk (Select stays disabled below it; backend already enforces).
- **Swap tickers in `mvp/src/api/assets.ts`** to match assets-api: QNT→HON, SPCX→GOOGL, BTQ→IBM (names, icons, colors).
- Scan-Badge button → Gemini (needs Rick's key).

### 3. Rate limits (replaces any transaction-cost idea)
- Manual retune button: rate-limited per user (+ UI feedback for the cooldown).
- Rebalance Frequency slider: drives automatic scheduled retunes (hourly cap) —
  `rebalance_hours` is mapped and stored but nothing dispatches jobs yet.
- QPU access: globally budgeted token bucket (assumptions on concurrent users
  and the <1hr-total-QPU-over-2-days math to be worked out).

### 4. QPU shakeout
The D-Wave provider is implemented (Ocean SDK, joins the race when
`DWAVE_API_TOKEN` is set; reports QPU access time). Remaining: run it against
Leap — verify embedding at 100 bits, tune `DWAVE_NUM_READS` vs the QPU budget,
and keep a dispatch seam for routing jobs through the Quip Network later.

## Notes

- **Persistence is in-memory** — lost on restart, single worker only (`--workers 1`). SQLite for booth-day durability.
- **Docs** — CLAUDE.md rewritten to the current model; MARKET_DATA_SPEC and IMPLEMENTATION_NOTES deleted (superseded by assets-api's openapi.yaml and git history). `docs/BACKEND_DAG.md` is current.
- **Brainstorm session (planned)** — improvements/suggestions pass over the whole flow: booth UX (what makes the race visceral on TV), leaderboard tie-breaks, Σ shrinkage, `TURNOVER_PENALTY_MULT` tuning, QPU showmanship vs cost.
