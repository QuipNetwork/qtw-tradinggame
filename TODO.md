# TODO

Backend for the QTW 2026 Trading Game. Core is built and tested (58 passing),
reconciled with the main-branch contract (3 sliders + 25-asset basket selection).
See `backend/README.md` to run and test, `docs/BACKEND_DAG.md` for the dataflow.

## Done

- **Contract v2** — 3 sliders (`rebalanceFrequency` discrete tiers / `riskPreference` / `maxPositionSize` relative to basket), 25-asset universe (14 crypto + 11 stocks, QNT included), per-agent basket (min 3 assets, fixed after sign-up), `email`/`reachOut`/`updatesOptIn` persisted.
- **Model** — cardinality dropped (basket expresses it): Gurobi solves a continuous QP; the QUBO has no indicator block; QUBO results are simplex-normalized, so **SA now genuinely competes** (feasible at all basket sizes).
- **D-Wave provider** — real Ocean-SDK implementation; token-gated entry into the race; QPU-access-time reporting; hermetic tests via sampler injection.
- **assets-api client** — `AssetsApiSource` implements `MarketDataSource` against `/v1/history` + `/v1/spot`, forward-filling stock market-hour gaps; flip `config.MARKET_DATA_SOURCE = "assets-api"` to use it.
- **API, persistence, orchestration, events, CLI** — as before, updated for the basket flow.

## Remaining (in order)

### 1. Run against real data
Stand up assets-api locally (Docker or clone + `make run`), let the 90-day
backfill finish, flip the source, and shake out real-data surprises (sparse
BTQ/SAF OTC bars, stablecoin near-zero variance → consider Σ shrinkage).
**SPCX has no provider** (private) — drop, substitute, or synthesize before booth;
QNT needs its provider routing enabled in assets-api now that it's public.

### 2. Frontend wiring
- `api/real.ts` (fetch + WS) + env-gate `api/index.ts` on `VITE_API_BASE` (mocks otherwise; Netlify preview unaffected).
- Local test loop: `uvicorn` on :8000 + `VITE_API_BASE=http://127.0.0.1:8000 npm run dev`.
- Welcome/Profile render `result.portfolio` from the server; drop the `sessionStorage` handoff; Profile sends sliders on retune; fix the `BoothTV` setState pattern.
- Mirror `MIN_BASKET_SIZE = 3` in the kiosk (Select stays disabled below it; backend already enforces).
- Scan-Badge button → Gemini (needs Rick's key).

### 3. Scheduled rebalances + QPU budget
`rebalance_hours` is mapped and stored but nothing dispatches scheduled jobs yet.
Add a scheduler loop honoring each agent's cadence, plus the global QPU
rate-limit math (3k users × cadence → keep total QPU time < 1 hr over 2 days).

### 4. QPU shakeout
The D-Wave provider is implemented (Ocean SDK, joins the race when
`DWAVE_API_TOKEN` is set; reports QPU access time). Remaining: run it against
Leap — verify embedding at 100 bits, tune `DWAVE_NUM_READS` vs the QPU budget,
and keep a dispatch seam for routing jobs through the Quip Network later.

## Notes

- **Persistence is in-memory** — lost on restart, single worker only (`--workers 1`). SQLite for booth-day durability.
- **Docs drift** — CLAUDE.md still describes the 5-slider / exactly-K model; refresh after the dust settles. `docs/MARKET_DATA_SPEC.md` is superseded by the assets-api OpenAPI contract. (`docs/BACKEND_DAG.md` is current.)
- **Brainstorm session (planned)** — improvements/suggestions pass over the whole flow: booth UX (what makes the race visceral on TV), turnover penalty + fee pairing for V1, leaderboard tie-breaks, Σ shrinkage, SA sweep tuning (~2.3s at 100 bits vs the 2s deadline), QPU showmanship vs cost.
