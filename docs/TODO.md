# TODO

QTW 2026 booth trading game. The core backend, frontend real API adapter, live
MTM websocket display, real QR generation, and assets-api client are in place.

Run/test refs:
- Backend: `backend/README.md`
- Dataflow: `docs/BACKEND_DAG.md`
- Frontend: `mvp/README.md`
- Market-data contract: sibling repo `../assets-api/openapi.yaml`

## Current State

- **Game contract**: 3 sliders plus K hold-count, 28-asset universe, min 15
  selected assets, $10K bankroll.
- **Market data**: `assets-api` is the default backend source; synthetic remains
  for tests/offline work. The redeployed assets-api spot loop defaults to 10s,
  and the backend MTM cadence now matches that by default.
- **Optimizer inputs**: no fabricated closed-hour returns. Missing stock hours
  and pre-listing gaps stay missing/NaN.
- **Live display**: frontend consumes backend websocket `AgentUpdate` messages.
- **TV display**: leaderboard, spotlight P&L chart, and QPU-vs-CPU solve winner
  share read from backend routes when `VITE_API_BASE` is set.
- **QR**: agent profile links default to `https://qtw.quip.network/p/{agentId}`.
- **Persistence**: `DATABASE_URL` selects SQL-backed stores for
  Supabase/Postgres; unset keeps the local/test in-memory path.
- **Scheduled rebalances**: optimized agents persist rebalance timestamps and
  the backend runs due background rebalances through the normal QPU-capable
  solver race.
- **Containerization/deploy**: backend Docker image build and GitLab deploy
  scaffold are in place; droplet provisioning and first live deploy remain.
- **QPU budget**: 8 QPU-admitted solves per agent per rolling 10 minutes
  (`QPU_BUDGET_MAX_ATTEMPTS=8`, the code default; production sets it explicitly).
  Manual over-budget requests return 429 and scheduled rebalances defer.
- **Email**: the Resend (HTTPS) provider is wired for opted-in signup confirmation
  emails when RESEND_API_KEY is set. Recurring hourly/daily result emails are not
  yet implemented.

## Next Work

### P0 - Persistence Production Rollout

The SQL-backed store path is implemented; production still needs operational
rollout and one real Supabase-backed smoke test.

- Verify the FastAPI container with Supabase `DATABASE_URL` and
  `APP_ENV=production` or `APP_ENV=booth`.
- Confirm table creation and startup hydration against the live Supabase
  project.
- Keep tests/offline work on forced in-memory stores; this is already wired in
  pytest fixtures.
- Keep the MTM hot path cheap: frequent valuation ticks should not write every
  tick.
- Store analytics valuation snapshots every 60s by default.
- Add/confirm a cleanup query for local/test rows before booth use.

Implementation notes:
- `DbAgentStore(AgentStore)` and `DbJobStore` are selected by `DATABASE_URL`.
- Human-paced writes: create agent, update sliders, update basket, apply solve.
- MTM can keep updating in memory and websocket output; durable valuation
  history should be sampled at the 60s snapshot cadence unless there is a clear
  booth analytics reason to increase it.

Environment/operations notes:
- Use one Supabase project for now. Local DB testing may point at that same
  project, so add a cleanup path for local/test rows before booth use.
- `DATABASE_URL` is backend-only. If it is set while running locally, local
  signups/solves will write to Supabase/Postgres.
- Add a source marker such as `environment` or `is_test` to separate local
  testing rows from booth rows.
- First production deployment should be one backend container with one Uvicorn
  worker. That still supports many phone websocket connections; it just means
  one process owns the MTM scheduler, in-process event bus, and solve queue.
- Email capture and sending are separate concerns: Supabase stores
  email/consent; FastAPI email sending uses the backend-only Resend API key.

### P1 - Production Deployment Wiring

Make the deployed frontend and backend agree on URLs and runtime env.

- Provision the DigitalOcean droplet, install Docker/Caddy, create
  `/opt/qtw/backend.env`, set GitLab CI/CD deploy variables, and run the manual
  deploy job.
- Netlify frontend env: set `VITE_API_BASE` to the deployed backend.
- Set `VITE_WS_BASE` only if websocket traffic uses a different host.
- Backend env: set `DATABASE_URL`, `ASSETS_API_BASE_URL`, `QR_BASE_URL`, and
  solver/QPU vars as needed.
- Keep `QR_BASE_URL=https://qtw.quip.network` unless the canonical domain
  changes.
- Current CORS origins are hardcoded in backend config; add a code change only
  if the deployed frontend/backend domains differ from the current values.

### P1 - Email Cadence Operations

Resend (HTTPS) email sending is implemented for the initial opt-in signup
confirmation. The hourly/daily update cadence still needs an operational scheduler pass.

- Wire recurring emails from the scheduler using each agent's `updateFrequency`.
- Send only to agents with `updatesOptIn=true` and a stored email address.
- Use the latest mark-to-market totals and avoid duplicate sends after restarts.
- Keep the Resend API key out of Netlify/browser env.

### P1 - QPU Budget Operations

Per-agent solve metering is implemented; booth operations may still need
aggregate budget visibility.

- Production env rule: 8 QPU-admitted solves per agent per rolling 10 minutes
  (`QPU_BUDGET_MAX_ATTEMPTS=8`, matching the code default).
- First solve, manual retune, and scheduled/background rebalance share the same
  per-agent budget.
- Manual over-budget optimize returns 429 + `Retry-After`.
- Scheduled over-budget rebalance defers `next_rebalance_at` to the next budget
  opening.
- Future enhancement: global token bucket metering actual `qpu_access_time`
  across all users.
- Optional future `/budget` endpoint for booth operations.

Budget note:
- Current estimate: ~55 min QPU over 2 days, ~170ms access/solve at 500 reads,
  about 19k QPU solves. This is enough for first solves plus a few manual
  retunes per attendee if cooldowns are enforced.

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
- **Scheduled rebalances**: Rebalance Frequency sets the next rebalance time;
  timestamps are persisted and shown on the phone profile.
- **QPU per-agent budget**: shared 3-per-10-minute admission gate for first
  solves, manual retunes, and scheduled rebalances.
- **Kiosk dense portfolio layout**: allocation bar keeps a fixed visible band,
  dense holding rows are constrained to the portfolio area, and the QR footer no
  longer overlaps price rows.
- **Backend Docker image**: `backend/Dockerfile`, `.dockerignore`,
  `backend/.env.example`, and `/healthz` support local and droplet container
  smoke tests.
- **Backend deploy automation scaffold**: GitLab CI can test, build, push the
  backend image to the GitLab registry, and manually deploy to a provisioned
  droplet.
- **assets-api spot freshness + MTM alignment**: assets-api owns provider
  fallback, rate-limit protection, and a 10s spot loop; QTW backend defaults
  `MTM_TICK_S` to 10s to publish after the spot cache can change.
- **TV routing stats**: `/routing-stats` computes QPU-vs-CPU winner share and
  provider breakdown from recorded solve jobs.
- **TV valuation history**: `/agents/{id}/valuation-history` drives the
  spotlight chart from sampled MTM history plus the current valuation.
- **Frontend dev landing**: `/` links to the latest locally created
  `/p/{agentId}` and `/kiosk/welcome?agent={agentId}` instead of hardcoded demo
  agent `a06`.

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
