# QTW 2026 Trading Game — Backend

Python backend for the booth trading competition. Phases 0/1/3/4/6 are built; it
runs end-to-end on a deterministic **synthetic** market (no network), so you can
exercise the whole pipeline today. See `../docs/BACKEND_DAG.md` for the dataflow
and `../TODO.md` for what's left.

## Setup

`uv` is the intended tool, but any venv works. Using the existing `.venv`:

```bash
cd backend
python3.12 -m venv .venv                 # first time only
.venv/bin/python -m pip install -e . pytest httpx
```

Gurobi (`gurobipy`) and SA (`dwave-neal`) install from PyPI with a free trial
license that comfortably fits this problem size.

## Run the automated tests

```bash
.venv/bin/python -m pytest -q             # 49 tests, ~8s
```

What each suite covers:

| File | What it checks |
|---|---|
| `test_slider_map.py` | 0–100 sliders → params; the inversions; `w_max` floor; `w_min` |
| `test_qubo_encoder.py` / `test_qubo_roundtrip.py` | QUBO shape/symmetry; decode round-trips within a quantum; `w_min` offset |
| `test_feasibility.py` | budget / box / exactly-K checks |
| `test_estimators.py` / `test_synthetic_market.py` | μ, Σ; deterministic history; moving spot |
| `test_solvers_synthetic.py` | Gurobi feasible; SA feasible & matches Gurobi; the race |
| `test_pnl.py` / `test_retune.py` | mark-to-market; trade diff + V0 fee |
| `test_persistence.py` / `test_job_pipeline.py` | stores + leaderboard; first-solve & retune end-to-end |
| `test_api.py` | HTTP flow, 404s, and a live WebSocket push (FastAPI TestClient) |

## Test from the CLI (no server needed)

`qtw` (or `python -m backend.cli`) exercises the pipeline against the configured
market source — handy for quick checks and for sanity-testing data later.

```bash
.venv/bin/qtw market                              # spot, hourly μ and vol per asset
.venv/bin/qtw optimize --risk 70 --diversification 50   # full solve → portfolio (exactly-K)
.venv/bin/qtw race --diversification 80           # one solver race, all providers + timing
```

Slider flags (`--risk`, `--trade-size`, `--holding-style`, `--diversification`,
`--trading-activity`) take 0–100; `market --tau <hours>` sets the μ lookback.

## Run the server

```bash
.venv/bin/python -m uvicorn backend.api.app:app --reload --workers 1
```

Then open `http://127.0.0.1:8000/docs` for interactive Swagger UI — the easiest
way to click through every endpoint.

## Test the API by hand

```bash
BASE=http://127.0.0.1:8000

# 1. Create an agent → returns agentId, qrUrl, bankroll
curl -s $BASE/agents -H 'content-type: application/json' -d '{
  "name":"Neo","handle":"neo",
  "sliders":{"tradingActivity":50,"riskPreference":70,"tradeSize":50,"holdingStyle":40,"diversification":50}
}'

# 2. Optimize (first solve). Use the agentId from step 1.
curl -s $BASE/agents/<AGENT_ID>/optimize -H 'content-type: application/json' -d '{}'
#    → RoutingResult: provider, providerType, solveTime, vsClassical, portfolio[], kind="first"

# 3. Retune with new sliders (kind="retune")
curl -s $BASE/agents/<AGENT_ID>/optimize -H 'content-type: application/json' \
  -d '{"sliders":{"tradingActivity":50,"riskPreference":90,"tradeSize":50,"holdingStyle":40,"diversification":80}}'

# 4. Leaderboard
curl -s $BASE/leaderboard
```

Things worth checking in the response:
- `portfolio` has exactly **K** entries (K from the Diversification slider) and the `pct` values sum to 100.
- `kind` is `"first"` then `"retune"`; `jobId` and `solvedAt` are populated.

## Test the live WebSocket

The MTM loop pushes a valuation every ~3s, and each optimize also pushes one.
With the server running and an agent that has optimized at least once:

```bash
.venv/bin/python - <<'PY'
import asyncio, json, websockets
AGENT = "<AGENT_ID>"
async def main():
    async with websockets.connect(f"ws://127.0.0.1:8000/agents/{AGENT}") as ws:
        for _ in range(3):
            print(json.loads(await ws.recv()))   # {plUSD, plPct, total}
asyncio.run(main())
PY
```

`ws://127.0.0.1:8000/tv/events` streams booth events (e.g. `new-agent`).
