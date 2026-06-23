# QTW 2026 Trading Game — Backend

Python backend for the booth trading competition. Reads market data from the
**assets-api** service by default; a deterministic synthetic source
(`MARKET_DATA_SOURCE=synthetic`) runs the whole pipeline offline. See
`../docs/BACKEND_DAG.md` for the dataflow and `../docs/TODO.md` for what's left.

## Setup

Use the backend `.venv`:

```bash
cd backend
python3.12 -m venv .venv                 # first time only
.venv/bin/python -m pip install -e . pytest httpx
```

Gurobi (`gurobipy`) and SA (`dwave-neal`) install from PyPI with a free trial
license that comfortably fits this problem size.

## Run the automated tests

```bash
.venv/bin/python -m pytest -q             # full backend suite
```

What each suite covers:

| File | What it checks |
|---|---|
| `test_slider_map.py` | 3 sliders → params; risk inversion; basket-relative caps; rebalance tiers; min basket |
| `test_qubo_encoder.py` / `test_qubo_roundtrip.py` | QUBO shape/symmetry; bit-grid round-trips; simplex normalization |
| `test_feasibility.py` | budget / box checks |
| `test_estimators.py` / `test_synthetic_market.py` | NaN-aware μ/Σ; variance floor; PSD repair; moving spot |
| `test_solvers_synthetic.py` | Gurobi feasible; SA feasible & matches Gurobi; the race |
| `test_assets_api.py` | assets-api client: grid alignment, no-fabrication NaN gaps, spot, errors |
| `test_pnl.py` | mark-to-market rollup |
| `test_persistence.py` / `test_job_pipeline.py` | in-memory and SQL-backed stores; first-solve & retune over the basket |
| `test_scheduler.py` | MTM websocket payloads and due scheduled rebalances |
| `test_solver_race_results.py` | solver-run metadata, infeasible/failed rows, winner reporting |
| `test_api.py` | HTTP flow, 404s/422s, and a live WebSocket push |

## Test from the CLI (no server needed)

`qtw` (or `python -m backend.cli`) exercises the pipeline against the configured
market source — handy for quick checks and for sanity-testing data later.

```bash
.venv/bin/qtw market                                  # spot, hourly μ and vol per asset
.venv/bin/qtw optimize --risk 70                      # full-universe solve → portfolio
.venv/bin/qtw race --max-position 80                  # one solver race, all providers + timing
```

Slider flags (`--risk`, `--max-position`, `--rebalance`) take 0–100;
`--assets` is a comma-separated basket (min 15, defaults to all 28).

## Market data (assets-api by default)

The backend uses the deployed assets-api service by default
(`https://asset-tracker.quip.network`). Override `ASSETS_API_BASE_URL` to point
at a local assets-api instance:

```bash
docker run -p 8080:8080 -v assets-data:/data \
  -e ALPACA_KEY_ID=... -e ALPACA_SECRET=... \
  registry.gitlab.com/quip.network/assets-api:latest
# wait for the 90-day backfill, check http://127.0.0.1:8080/healthz
```

Returns use real bars only — closed hours and pre-listing gaps stay missing
(never zero-filled), so a stock's overnight jump is excluded and freshly-listed
names aren't read as artificially calm; the covariance estimator handles the
ragged data (pairwise overlap, variance floor, PSD repair). No service running?
`MARKET_DATA_SOURCE=synthetic` switches everything (server, CLI, tests already
pin it) to the deterministic offline source.

## Enable the D-Wave QPU

The QPU joins the solver race only when a Leap token is present:

```bash
export DWAVE_API_TOKEN=...   # from cloud.dwavesys.com
.venv/bin/qtw race           # field becomes gurobi, sa, dwave
```

Reported D-Wave solve time is QPU access time, not network round-trip. The
provider uses the clique sampler (cached embeddings — no per-solve embedding
search) and picks the best *feasible* anneal read, not just the lowest-energy
one.

QPU admission is budgeted per agent: 8 QPU-admitted solves per rolling
10 minutes. First solve, manual retune, and scheduled rebalance share that
budget. Manual over-budget optimize returns HTTP 429 + `Retry-After`;
scheduled over-budget rebalance defers `nextRebalanceAt`.

Tuning knobs are env vars: `DWAVE_NUM_READS` (500), `DWAVE_ANNEAL_TIME_US`
(100), `DWAVE_CHAIN_STRENGTH_PREFACTOR` (3). `qtw verify-dwave [--assets …]`
submits one QUBO to Leap and reports chip, embedding, chain breaks, timing, and
feasible-read stats. `GUROBI_IN_RACE=0` previews the production field — Gurobi
stays an offline oracle and the live race is SA vs the QPU.

## Run the server

```bash
.venv/bin/python -m uvicorn backend.api.app:app --reload --workers 1
```

Then open `http://127.0.0.1:8000/docs` for interactive Swagger UI — the easiest
way to click through every endpoint.

For a container or remote host, the process must bind to `0.0.0.0`:

```bash
.venv/bin/python -m uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

Keep one worker for the first production deployment. The websocket event bus,
MTM scheduler, and scheduled rebalance loop are in-process.

## Run with Docker

Build from the repo root so Docker can see `backend/`:

```bash
docker build -f backend/Dockerfile -t qtw-backend:local .
```

Run an offline smoke test with synthetic market data:

```bash
docker run --rm -p 8001:8000 \
  -e APP_ENV=local-container \
  -e MARKET_DATA_SOURCE=synthetic \
  -e GUROBI_IN_RACE=0 \
  qtw-backend:local
```

Run against the normal assets-api path with a local env file:

```bash
cp backend/.env.example backend/.env.local
# edit backend/.env.local if you want DATABASE_URL or other real services
docker run --rm --env-file backend/.env.local -p 8001:8000 qtw-backend:local
```

Check the container:

```bash
curl http://127.0.0.1:8001/healthz
```

## Test the API by hand

```bash
BASE=http://127.0.0.1:8000

# 1. Create an agent → returns agentId, qrUrl, bankroll, token
CREATE_RESPONSE=$(curl -s $BASE/agents -H 'content-type: application/json' -d '{
  "name":"Neo","email":"neo@example.com",
  "sliders":{"rebalanceFrequency":50,"riskPreference":70,"maxPositionSize":50},
  "assets":["BTC","ETH","SOL","USDC","IONQ","QBTS","RGTI","IBM","GOOGL","NVDA","MSFT","AMZN","HON","SAF","SPCX"]
}')
printf '%s\n' "$CREATE_RESPONSE"
AGENT_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["agentId"])' <<<"$CREATE_RESPONSE")
TOKEN=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$CREATE_RESPONSE")

# 2. Optimize (first solve). Use the agentId from step 1.
curl -s "$BASE/agents/$AGENT_ID/optimize" \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{}'
#    → RoutingResult: provider, providerType, solveTime, solverResults[],
#      portfolio[], kind="first", nextRebalanceAt

# 3. Retune — new sliders and/or a re-selected basket (liquidates + reallocates)
curl -s "$BASE/agents/$AGENT_ID/optimize" \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"sliders":{"rebalanceFrequency":50,"riskPreference":90,"maxPositionSize":80},"assets":["BNB","XRP","USDT","DOGE","HYPE","ZEC","ALGO","FIL","RENDER","STRK","ARQQ","LAES","QUBT","IBM","SPCX"]}'

# 4. Leaderboard
curl -s $BASE/leaderboard
```

Things worth checking in the response:
- `portfolio` holds **every basket asset** (min-position floor) and the `pct` values sum to 100.
- `kind` is `"first"` then `"retune"`; `jobId` and `solvedAt` are populated.
- `nextRebalanceAt` and `rebalanceIntervalHours` are populated after a solve.
- `qpuBudget` reports used/limit/window and the next QPU opening when D-Wave is
  configured or prior QPU attempts exist.
- `solverResults` lists every solver that ran, including infeasible, failed, or
  timed-out providers.

## Test the live WebSocket

The MTM loop pushes a valuation every `MTM_TICK_S` seconds (10s by default,
matching assets-api's spot loop), and each optimize also pushes one.
Scheduled rebalances run in a separate loop and use the same QPU-capable
optimization path as manual retunes. With the server running and an agent that
has optimized at least once:

```bash
.venv/bin/python - <<'PY'
import asyncio, json, websockets
AGENT = "<AGENT_ID>"
TOKEN = "<TOKEN>"
async def main():
    async with websockets.connect(f"ws://127.0.0.1:8000/agents/{AGENT}?t={TOKEN}") as ws:
        for _ in range(3):
            print(json.loads(await ws.recv()))   # {plUSD, plPct, total, holdings, asOf, stale, nextRebalanceAt}
asyncio.run(main())
PY
```

`ws://127.0.0.1:8000/tv/events` streams booth events (e.g. `new-agent`).

## Production wiring status

See `../docs/DEPLOY.md` for the consolidated DigitalOcean Droplet + Docker
operator runbook, production environment variables, Supabase/Postgres behavior,
and Proton SMTP setup.

GitLab CI now includes backend test/build image jobs and a manual droplet deploy
job. The deploy job becomes usable after the droplet is provisioned, Docker/Caddy
are installed, `/opt/qtw/backend.env` exists, and the GitLab CI deploy variables
are set. Proton SMTP is wired for opted-in signup confirmation emails when SMTP env is
present; recurring hourly/daily result emails still need scheduler work.
