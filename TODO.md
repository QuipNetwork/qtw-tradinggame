# TODO

QTW 2026 booth trading game. The core backend, frontend real API adapter, live
MTM websocket display, real QR generation, and assets-api client are in place.

Run/test refs:
- Backend: `backend/README.md`
- Dataflow: `docs/BACKEND_DAG.md`
- Frontend: `mvp/README.md`
- Market-data contract: sibling repo `../assets-api/openapi.yaml`

## Current State

- **Game contract**: 3 sliders, 28-asset basket, min 3 assets, $10K bankroll.
- **Market data**: `assets-api` is the default backend source; synthetic remains
  for tests/offline work.
- **Optimizer inputs**: no fabricated closed-hour returns. Missing stock hours
  and pre-listing gaps stay missing/NaN.
- **Live display**: frontend consumes backend websocket `AgentUpdate` messages.
- **QR**: agent profile links default to `https://qtw.quip.network/p/{agentId}`.
- **Persistence**: still in-memory in the QTW backend; not production-durable.

## Next Work

### P0 - Durable Backend Persistence

Replace process-local in-memory stores before production deployment.

- Persist agents, holdings, jobs, and valuations in Supabase/Postgres.
- Keep tests/offline work on forced in-memory stores.
- Keep the MTM hot path cheap: frequent valuation ticks should not write every
  tick unless we intentionally add sampled/history persistence.
- On startup, load the active working set from the DB.

Implementation notes:
- The target shape discussed is `DbAgentStore(AgentStore)` and `DbJobStore`,
  selected by `DATABASE_URL`.
- Human-paced writes: create agent, update sliders, update basket, apply solve.
- MTM can keep updating in memory and websocket output; decide separately if
  leaderboard/valuation snapshots need periodic durable writes.

### P0 - assets-api Spot Freshness

Move market-price freshness control into `../assets-api`; QTW backend should
consume the resulting spot contract.

- Split spot refresh cadence from history/bar refresh.
- Keep history bars hourly-oriented for μ/Σ.
- Make `/v1/spot` refresh faster with an env-tunable cadence, likely 30s or
  60s to start.
- Choose the cadence against Alpaca, Massive, and CoinGecko rate limits.
- Preserve per-ticker `stale` metadata from assets-api.

Implementation notes:
- assets-api owns provider fallback, rate-limit protection, spot caching, and
  quote freshness.
- QTW backend owns holdings, MTM, leaderboard, and frontend websocket pushes.
- Frontend wording should be `Live` when all held quotes are fresh and
  `Last close` when any holding uses a stale/last-known quote.

### P0 - Align Backend MTM Cadence

After assets-api exposes the intended spot refresh cadence, align QTW backend
MTM publishing to it.

- Current backend MTM cadence is still 3s.
- If assets-api spot refresh is 30s, backend MTM should usually publish around
  30s, or publish on an assets-api price-update signal later.
- Avoid recomputing/pushing the same valuation every 3s when the spot cache has
  not changed.

### P1 - Production Deployment Wiring

Make the deployed frontend and backend agree on URLs and runtime env.

- Netlify frontend env: set `VITE_API_BASE` to the deployed backend.
- Set `VITE_WS_BASE` only if websocket traffic uses a different host.
- Backend env: set `DATABASE_URL`, `ASSETS_API_BASE_URL`, `QR_BASE_URL`, CORS
  origins, and solver/QPU vars as needed.
- Keep `QR_BASE_URL=https://qtw.quip.network` unless the canonical domain
  changes.

### P1 - QPU Budget And Retune Rate Limits

Implement booth-safe solve metering before open use.

- Global token bucket metering QPU milliseconds.
- Debit actual `qpu_access_time` per solve.
- First solve and manual retune can be QPU-eligible.
- Scheduled/invisible rebalances should run CPU-only.
- Add per-agent manual retune cooldown, likely around 5 minutes.
- Return 429 + `Retry-After`; frontend should show the countdown.
- Optional `/budget` endpoint for booth operations.

Budget note:
- Current estimate: ~55 min QPU over 2 days, ~170ms access/solve at 500 reads,
  about 19k QPU solves. This is enough for first solves plus a few manual
  retunes per attendee if cooldowns are enforced.

### P1 - Scheduled Rebalances

Wire the Rebalance Frequency slider into actual scheduled retunes.

- Slider already maps to tiers: 24h, 8h, 4h, 2h, 1h.
- Hourly remains the hard cap.
- Scheduled jobs should be CPU-only unless explicitly approved otherwise.
- Manual retune remains the user-visible race moment.

### P1 - QPU Hardware Shakeout

D-Wave provider is implemented and token-gated, but hardware verification still
needs a final pass.

- Run `qtw verify-dwave`.
- Run `qtw verify-dwave --assets BTC,ETH,SOL,IONQ,QBTS,RGTI`.
- Confirm feasible reads at current large-basket settings.
- Tune `DWAVE_NUM_READS` versus QPU budget if needed.
- Keep a dispatch seam for routing jobs through Quip Network later.

### P2 - Frontend Polish

Clean up temporary UI/state work after persistence and freshness are done.

- Drop temporary `sessionStorage` handoff for optimize/QR state once durable
  persistence is available.
- Fix the `BoothTV` setState pattern.
- Keep kiosk/phone labels consistent: `Live` vs `Last close`.
- Scan-Badge button -> Gemini once Rick's key/integration is ready.

## Done

- **Contract v2**: 3 sliders, 28-asset universe, per-agent basket, min basket
  size, email/reach-out/update opt-in fields.
- **Optimization model**: basket-sized mean-variance QP; no cardinality
  constraint; QUBO path for SA/D-Wave; Gurobi as dev/oracle solver.
- **No-fabrication returns**: closed stock hours and pre-listing gaps stay
  missing; μ/Σ estimators handle ragged real data.
- **assets-api client**: `/v1/history` and `/v1/spot` implemented through the
  `MarketDataSource` protocol.
- **Real frontend adapter**: `VITE_API_BASE` selects `real.ts`; mocks remain the
  offline/default frontend fallback.
- **Live MTM display**: backend websocket pushes richer `AgentUpdate` payloads;
  kiosk/phone consume live totals and holdings.
- **QR generation**: kiosk renders scannable profile QR codes.
- **D-Wave provider**: Ocean SDK path exists; joins the race only when
  `DWAVE_API_TOKEN` is set.

## Watch Items

- assets-api currently serves indexed/cached spot prices, not tick-by-tick
  provider pass-through.
- assets-api backfill means fetching real historical bars; it is not
  forward-filling missing stock-market hours.
- `SAF` uses the SAFRY ADR path in assets-api; absolute price can differ from
  Euronext SAF, while returns should track the listing.
- `SPCX` has short post-IPO history until more bars accrue.
- Stablecoins can have near-zero variance; keep variance floors and PSD repair
  in mind when reviewing optimizer output.
