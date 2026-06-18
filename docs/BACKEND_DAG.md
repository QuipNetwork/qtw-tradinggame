# Backend DAG - System Dataflow

This is the current backend shape for the QTW 2026 trading game: kiosk signup,
phone retunes, live mark-to-market updates, scheduled rebalances, persistence,
and the solver race.

## Current Status

- FastAPI is the long-lived backend process. It owns HTTP routes, websocket
  routes, the in-process event bus, the MTM loop, and the scheduled rebalance
  loop.
- `DATABASE_URL` selects SQL-backed stores for Supabase/Postgres. When unset,
  the same store interfaces use in-memory dictionaries for local/offline work.
- `MARKET_DATA_SOURCE` defaults to `assets-api`; `synthetic` remains available
  for tests and offline demos.
- D-Wave joins the race only when `DWAVE_API_TOKEN` is set. Gurobi should stay
  out of the production race with `GUROBI_IN_RACE=0`.
- Scheduled rebalances are implemented. They call the same optimization path as
  manual retunes, so they are QPU-capable when D-Wave is configured.
- The backend Docker image build is implemented. Proton SMTP sending, QPU budget
  limits, and droplet deploy automation are still pending.

## High-Level DAG

```mermaid
flowchart TB
    %% ===== Frontend =====
    subgraph FE["Frontend MVP"]
        K["Kiosk SignUp<br/>/kiosk"]
        W["Kiosk Welcome<br/>/kiosk/welcome"]
        P["Phone Profile<br/>/p/:agentId"]
        TV["TV views<br/>leaderboard + events"]
    end

    %% ===== API =====
    subgraph API["FastAPI HTTP / WS"]
        A1["POST /agents<br/>create agent + QR URL"]
        A2["GET /agents/:id<br/>load profile config"]
        A3["POST /agents/:id/optimize<br/>first solve, retune, scheduled solve"]
        A4["GET /leaderboard"]
        WS1["WS /agents/:id<br/>live valuation"]
        WS2["WS /tv/events<br/>new-agent/rank events"]
    end

    %% ===== Orchestration =====
    subgraph ORCH["Orchestration"]
        JOB["job.py<br/>build problem -> race -> allocate -> persist"]
        MTM["scheduler.py<br/>MTM loop every MTM_TICK_S"]
        REB["scheduler.py<br/>scheduled rebalance check"]
    end

    %% ===== Domain =====
    subgraph FIN["Financial Domain"]
        SL["slider_map.py<br/>sliders -> gamma, caps, cadence"]
        ER["expected_return.py<br/>mu from real returns"]
        CV["covariance.py<br/>Sigma from pairwise real overlap"]
        QP["PortfolioProblem<br/>mean-variance box QP"]
        ENC["qubo_encoder.py<br/>QP -> QUBO for SA/D-Wave"]
        DEC["qubo_decoder.py<br/>bitstrings -> weights"]
        PNL["pnl.py<br/>holdings x spot -> AgentUpdate"]
        BASKET["basket.py<br/>28-asset universe"]
    end

    %% ===== Market data =====
    subgraph DATA["Market Data"]
        SRC["prices/source.py<br/>assets-api or synthetic"]
        ASSETS[/"assets-api<br/>spot + hourly history"/]
    end

    %% ===== Solvers =====
    subgraph SOLV["Solver Race"]
        RTR["router.py<br/>parallel providers; fastest feasible solve/access time wins"]
        GU["Gurobi<br/>continuous QP; dev/oracle"]
        SA["Simulated Annealing<br/>QUBO on CPU"]
        DW["D-Wave Advantage<br/>QUBO on QPU with DWAVE_API_TOKEN"]
        FEAS["feasibility.py<br/>budget + box gate"]
    end

    %% ===== Persistence =====
    subgraph PERS["Persistence"]
        AG["AgentStore / DbAgentStore<br/>config, basket, holdings, valuation"]
        JBS["JobStore / DbJobStore<br/>winner audit + solve snapshots"]
        VS["valuation_snapshots<br/>sampled analytics history"]
        LB["leaderboard.py<br/>rank from current agent totals"]
    end

    %% ===== Events =====
    subgraph EV["Events"]
        BUS["bus.py<br/>in-process pub/sub"]
    end

    K --> A1
    K --> A3
    W --> A2
    W --> WS1
    P --> A2
    P --> A3
    P --> WS1
    TV --> A4
    TV --> WS2

    A1 --> AG
    A1 --> BUS
    A2 -.-> AG
    A3 --> JOB
    A4 -.-> LB

    JOB --> SL
    JOB --> BASKET
    JOB --> SRC
    SRC -.-> ASSETS
    SRC --> ER
    SRC --> CV
    ER --> QP
    CV --> QP
    SL --> QP
    QP --> ENC
    QP --> RTR
    ENC --> RTR
    RTR --> GU
    RTR --> SA
    RTR --> DW
    GU --> FEAS
    SA --> FEAS
    DW --> FEAS
    FEAS --> DEC
    DEC --> JOB

    JOB --> AG
    JOB --> JBS
    JOB --> BUS
    JOB --> A3

    MTM -.-> AG
    MTM --> SRC
    MTM --> PNL
    PNL --> AG
    PNL --> VS
    PNL --> LB
    PNL --> BUS

    REB -.-> AG
    REB --> JOB

    BUS --> WS1
    BUS --> WS2

    classDef external fill:#fff4e6,stroke:#cc8800,color:#5c3d00
    classDef storage fill:#e6f2ff,stroke:#0066cc,color:#0d2b52
    classDef solver fill:#f0e6ff,stroke:#6600cc,color:#2a0a52

    class ASSETS external
    class AG,JBS,VS,LB storage
    class GU,SA,DW,RTR solver
```

## Main Flows

### 1. Create Agent

`POST /agents` validates the selected basket, stores the agent config, and
returns:

- `agentId`
- `qrUrl`, built from `QR_BASE_URL/p/{agentId}`
- starting bankroll

No solve happens here. The kiosk calls optimize after creation.

### 2. First Solve / Manual Retune

`POST /agents/:id/optimize` runs the full optimization pipeline.

1. Load the agent from `AgentStore`.
2. Apply any changed sliders or basket.
3. Fetch hourly returns from the configured market data source.
4. Estimate expected returns and covariance from real returns only.
5. Build the mean-variance problem:

   minimize: gamma over 2 times portfolio variance minus expected return

   subject to: weights sum to 1, and every selected asset stays between
   `w_min` and `w_max`

6. Race providers:
   - Gurobi solves the continuous QP when enabled.
   - Simulated annealing solves the QUBO on CPU.
   - D-Wave solves the same QUBO on QPU when `DWAVE_API_TOKEN` is set.
7. Keep all provider results for display/audit.
8. Pick the feasible result with the lowest reported solve/access time.
9. Liquidate the previous basket at spot and allocate the full value into the
   winning weights.
10. Persist holdings, solve metadata, solve snapshots, and rebalance timestamps.
11. Publish an immediate `AgentUpdate` over the per-agent websocket.

Current code treats every solve as a fresh allocation. There is no turnover
penalty and no transaction fee in the live path.

### 3. Scheduled Rebalance

`run_scheduled_rebalance_loop` checks active agents every
`REBALANCE_CHECK_TICK_S`.

- Active means the agent has holdings from at least one prior solve.
- If `next_rebalance_at` is missing on a hydrated active agent, the backend
  initializes it from the current slider cadence.
- When due, the loop calls `run_optimization` with the existing sliders and
  basket.
- Because it uses the normal optimization path, scheduled/background rebalances
  are QPU-capable when D-Wave is configured.
- Failures are logged and retried after `REBALANCE_RETRY_BACKOFF_S`.

This loop is separate from MTM so a solve does not block valuation pushes.

### 4. Mark-To-Market

`run_mtm_loop` runs every `MTM_TICK_S`.

1. Collect all tickers currently held by active agents.
2. Fetch one spot snapshot for that ticker set.
3. Revalue each agent's units against spot.
4. Update the in-memory hot path with `set_valuation`.
5. Persist sampled analytics rows every `VALUATION_SNAPSHOT_INTERVAL_S` when
   SQL-backed stores are enabled.
6. Publish an `AgentUpdate` over websocket.

The frequent MTM path does not write every tick to Postgres. Durable valuation
history is sampled for analytics.

## Solver Race Semantics

The race does not stop at the first feasible response anymore. The router
collects finished provider results until the overall deadline, marks infeasible
and failed providers, and then chooses the feasible solution with the lowest
reported solve/access time.

Important details:

- D-Wave's displayed time is QPU access time, not network round-trip.
- Gurobi should be disabled in production with `GUROBI_IN_RACE=0`.
- The legacy `vsClassical` field remains for older clients, but the frontend now
  renders the ranked `solverResults` list and percentage margin.
- If no provider returns a feasible solution before the deadline, the API returns
  `503`.

## Persistence Semantics

The code uses store interfaces everywhere:

- `AgentStore` / `DbAgentStore`
- `JobStore` / `DbJobStore`

Selection is environment-driven:

- `DATABASE_URL` unset: in-memory store.
- `DATABASE_URL` set: SQL-backed store, usually Supabase/Postgres.

`DbAgentStore` subclasses the in-memory store. On startup it loads the working
set from the database into memory. Human-paced operations write through to SQL:

- create agent
- update sliders
- update basket
- apply solve
- initialize missing rebalance timestamps

MTM valuations update the in-memory working set every tick. Durable valuation
snapshots are sampled separately.

## Runtime Boundaries

- Frontend env (`VITE_API_BASE`, optional `VITE_WS_BASE`) belongs in Netlify.
- Backend env (`DATABASE_URL`, `ASSETS_API_BASE_URL`, `DWAVE_API_TOKEN`,
  `QR_BASE_URL`, SMTP secrets later) belongs only on the backend host/container.
- Supabase hosts Postgres only; the browser never connects to the database.
- assets-api owns provider fallback, rate-limit protection, quote freshness, and
  history/spot caching.
- QTW backend owns agent state, solver dispatch, MTM, scheduled rebalances,
  leaderboard, and websocket pushes.

## Single-Worker Constraint

The current event bus and schedulers are in-process. Run one Uvicorn worker for
the first production deployment:

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

Multiple backend workers would need an external event bus and scheduler
coordination, such as Redis pub/sub plus a distributed lock, or Postgres
LISTEN/NOTIFY plus advisory locks.

## Still Missing

- Proton SMTP sender: email/consent fields are stored, but no backend email
  sender exists yet.
- Droplet deploy automation: the Dockerfile exists, but CI/registry/pull-and-
  restart wiring is still pending.
- QPU budget and retune rate limits: scheduled rebalances and manual retunes are
  QPU-capable, but token-bucket enforcement is still pending.
- assets-api spot freshness: QTW consumes the spot contract; faster freshness
  belongs in `../assets-api`.
- MTM cadence alignment: once assets-api spot freshness is finalized, align
  `MTM_TICK_S` with that cadence.
