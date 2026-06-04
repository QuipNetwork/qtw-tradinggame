# TODO

Backend for the QTW 2026 Trading Game. The core is built and tested (49 passing)
on a synthetic market stand-in. See `backend/README.md` to run and test, and
`docs/BACKEND_DAG.md` for the dataflow.

## Done

- **Math core** — slider_map, estimators (μ, Σ), QUBO encode/decode, retune, feasibility.
- **Solver race** — Gurobi (MIQP) + SA (QUBO), first feasible wins; exactly-K enforced.
- **API** — 4 HTTP endpoints + agent/TV WebSockets (FastAPI).
- **Persistence + orchestration** — in-memory stores, optimize pipeline, MTM loop.
- **Events** — pub/sub bus (per-agent updates, new-agent TV event).

## Remaining (in order, all pending)

### 1. Live market data
Replace the synthetic source with CoinGecko behind the existing
`MarketDataSource` interface, then flip `config.MARKET_DATA_SOURCE`:
- `prices/history.py` — hourly OHLCV → returns, cached (mind the rate limits).
- `prices/oracle.py` — live spot, batched in one call.
- Shrink Σ for stablecoins (USDC ≈ constant → near-singular).

### 2. Frontend wiring
- Widen `api/types.ts`: 15-asset basket; `RoutingResult.kind / jobId / solvedAt / feeUsd`; `bankroll` on submit.
- Add `api/real.ts` (fetch + WS) and env-gate `api/index.ts` on `VITE_API_BASE` (mocks otherwise, so the preview keeps working).
- Clean-flow fixes: Welcome renders `result.portfolio`; drop the `sessionStorage` handoff; Profile sends sliders on retune; fix the `BoothTV` setState pattern.

### 3. D-Wave provider (last)
Implement `solvers/providers/dwave.py` to solve the **QUBO** (the same one SA
solves) on D-Wave Advantage via the Ocean SDK, and add it to the race. Needs a
Leap API token. The stub/contract is already in place.

## Notes

- **Persistence is in-memory** (process dicts) — fine for booth day, but lost on
  restart and single-worker only. Run uvicorn with `--workers 1`. Swap for
  SQLite/Postgres for durability.
- **Later polish** — config/secrets (`.env`), structured logging per job,
  deploy + health check, optimize-endpoint rate limit.
- **SA at N=15** — SA often lands just outside the strict budget tolerance
  (`Σw ≈ 1.007`), so Gurobi wins the race; `qtw race` shows every solver's
  allocation. Loosening ε for QUBO solvers or tuning penalties/bits is pending.
- **Doc drift** — the model now floors `w_max` at `1/K` and enforces exactly-K
  via a min position `w_min`; reflect in CLAUDE.md §5.1/§5.4/Q1 when convenient.
