# Backend DAG — System dataflow

Full dataflow for the QTW 2026 Trading Game backend, from frontend touch through
solver race back to live MTM updates. Solid arrows = synchronous data flow;
dotted arrows = reads from persistence or external data.

**Legend.** **Red dashed = pending (not yet built):** CoinGecko + `prices/history`
+ `prices/oracle` (live market data) and the D-Wave provider. A deterministic
**synthetic source stands in for the data layer today**, behind the same
interface. Blue = persistence stores; purple = live solvers; the frontend MVP
runs on **mocks** until it's wired to the real API.

**What's left, in order:** ① live market data → ② frontend wiring → ③ D-Wave provider (last).

```mermaid
flowchart TB
    %% ===== Frontend =====
    subgraph FE["Frontend (MVP)"]
        K["Kiosk SignUp<br/>(/kiosk)"]
        W["Kiosk Welcome<br/>(/kiosk/welcome)"]
        P["Phone Profile<br/>(/p/:agentId)"]
        TVA["TV StateA<br/>Leaderboard"]
        TVB["TV StateB<br/>Spotlight"]
        TVC["TV StateC<br/>Welcome splash"]
        TVD["TV StateD<br/>New-agent splash"]
    end

    %% ===== API =====
    subgraph API["HTTP / WS API"]
        EP1["POST /agents"]
        EP2["GET /agents/:id"]
        EP3["POST /agents/:id/optimize<br/>(payload: sliders?)"]
        EP4["GET /leaderboard"]
        EP5["WS /agents/:id"]
        EP6["WS /tv/events"]
    end

    %% ===== Orchestration =====
    subgraph ORCH["Orchestration"]
        JOB["job.py<br/>end-to-end pipeline"]
        SCHED["scheduler.py<br/>Σ refresh · MTM tick"]
    end

    %% ===== Financial / domain =====
    subgraph FIN["Financial (domain-aware)"]
        SM["slider_map.py<br/>0-100 → γ,w_max,w_min,τ,K,λ_t"]
        CE["estimators/covariance.py<br/>Σ from 720h window"]
        RE["estimators/expected_return.py<br/>μ from τ-h window"]
        QE["qubo_encoder.py<br/>MIQP + bit-discretized QUBO"]
        QD["qubo_decoder.py<br/>bitstring → weights"]
        RT["retune.py<br/>diff w_old→w_new"]
        PNL["pnl.py<br/>holdings × spot → AgentUpdate"]
        BASKET["basket.py<br/>15 tickers metadata"]
    end

    %% ===== Market data =====
    subgraph DATA["Market data"]
        SRC["prices/synthetic<br/>stand-in source (live)"]
        HIST[("prices/history<br/>hourly OHLCV cache")]
        ORACLE["prices/oracle<br/>live spot"]
        COINGECKO[/"CoinGecko<br/>(external)"/]
    end

    %% ===== Solvers =====
    subgraph SOLV["Solvers (race · first feasible wins)"]
        RTR["router.py<br/>parallel dispatch (ThreadPoolExecutor)"]
        GU["providers/gurobi.py<br/>native MIQP<br/>CPU role + offline oracle"]
        SA["providers/sa.py<br/>QUBO via neal<br/>CPU role"]
        DW["providers/dwave.py<br/>QUBO on Advantage QPU<br/>QPU role · pending"]
        FEAS["feasibility.py<br/>budget · box · K check"]
    end

    %% ===== Persistence =====
    subgraph PERS["Persistence"]
        AG[("agents<br/>config + holdings + history")]
        JOBS[("jobs<br/>audit log per Q hash")]
        LB[("leaderboard<br/>rank by total")]
    end

    %% ===== Events =====
    subgraph EV["Events"]
        BUS["bus.py<br/>pub/sub"]
    end

    %% ===== Config =====
    CFG["config.py<br/>bankroll · ε · b · K bounds"]

    %% ===== Frontend → API =====
    K -->|"submitAgent(config)"| EP1
    K -->|"requestOptimization(id)"| EP3
    P -->|"retune w/ sliders"| EP3
    P -->|"subscribeAgent"| EP5
    W -->|"getAgent(id)"| EP2
    TVA -->|"getLeaderboard"| EP4
    TVA -.->|"subscribe rank events"| EP6
    TVD -.->|"subscribe new-agent"| EP6

    %% ===== API → Orchestration / Persistence =====
    EP1 --> AG
    EP1 --> CFG
    EP2 -.-> AG
    EP3 --> JOB
    EP4 -.-> LB

    %% ===== Pipeline =====
    JOB --> SM
    SM -.->|"τ"| RE
    SM -->|"γ, w_max, w_min, K, λ_t"| QE
    BASKET --> RE
    BASKET --> CE
    SRC --> RE
    SRC --> CE
    CE -->|"Σ (15×15)"| QE
    RE -->|"μ (15)"| QE
    AG -.->|"w_prev on retune"| QE
    CFG -.->|"b, λ_sum, λ_K"| QE

    QE -->|"MIQP (Gurobi) · QUBO (SA, D-Wave)"| RTR
    RTR -->|"native MIQP"| GU
    RTR -->|"QUBO"| SA
    RTR -->|"QUBO"| DW
    GU --> FEAS
    SA --> FEAS
    DW --> FEAS
    FEAS -->|"first feasible wins"| QD

    QD -->|"PortfolioEntry[]"| RT
    AG -.->|"current holdings"| RT
    SRC -.->|"spot for trade list"| RT
    RT -->|"new holdings"| AG
    RT -->|"Q hash, provider, time"| JOBS
    RT -->|"new agent / rank event"| BUS
    RT -->|"RoutingResult"| EP3

    %% ===== MTM loop =====
    SCHED -->|"MTM tick (~3s)"| PNL
    AG -.->|"holdings"| PNL
    SRC -.->|"spot"| PNL
    PNL -->|"AgentUpdate"| AG
    PNL -->|"total = bankroll + P&L"| LB
    PNL -->|"AgentUpdate"| BUS

    %% ===== Events fanout =====
    BUS -->|"per-agent updates"| EP5
    BUS -->|"TV events (new agent, rank reshuffle)"| EP6

    %% ===== Pending data path =====
    COINGECKO -.-> HIST
    COINGECKO -.-> ORACLE
    HIST -.->|"pending"| SRC
    ORACLE -.->|"pending"| SRC

    %% ===== Styling =====
    classDef planned fill:#ffe3e3,stroke:#cc1111,stroke-dasharray: 4 3,color:#7a0000
    classDef storage fill:#e6f2ff,stroke:#0066cc,color:#0d2b52
    classDef solver fill:#f0e6ff,stroke:#6600cc,color:#2a0a52

    class AG,JOBS,LB storage
    class SA,GU solver
    class COINGECKO,HIST,ORACLE,DW planned
```

## Reading the DAG

- **Top → bottom = user request flow**: frontend kiosk/phone touch → API → orchestration job → financial pipeline → solver race → decode → persist → respond.
- **Bottom = MTM background loop**: the scheduler ticks the PnL module every few seconds, revalues holdings against the current spot, updates persistence, and pushes deltas over WS.
- **Dotted arrows = reads** (from persistence or external data); solid arrows = synchronous data flow.
- **Data layer**: the estimators and PnL read from `prices/synthetic` today (live). The red-dashed `history` / `oracle` / CoinGecko path replaces it later behind the same interface — no pipeline change.
- **Three solver paths converge at `feasibility.py`** — first feasible wins. Gurobi additionally serves as the offline oracle (separate from the race).

## Solver race — how it connects

One canonical problem fans out to the solvers in two encodings — MIQP for Gurobi,
the bit-discretized QUBO for SA and D-Wave — and the **first feasible** answer wins.

- **The canonical problem.** `orchestration/job.py` assembles a `MIQPProblem`
  (`financial/types.py`) from the slider params (`slider_map.py`), the estimates
  (μ, Σ), and `w_prev` on a retune. That single object is the source of truth.
- **The router** (`solvers/router.py::race`) encodes the QUBO once, hashes it for
  the audit log, and dispatches the providers concurrently on a thread pool (the
  solve work releases the GIL). It takes the first feasible result and keeps the
  runner-up for the `vsClassical` baseline (decision Q7).
- **Encodings.** Gurobi reads the MIQP natively; SA and D-Wave solve the QUBO and
  decode the winning bitstring (`qubo_decoder.py`) to weights. Gurobi is also the
  offline oracle that calibrates penalty weights.
- **Feasibility gate** (`solvers/feasibility.py`) is identical for all three —
  budget `|Σwᵢ−1| < ε`, box `0 ≤ wᵢ ≤ w_max`, **exactly-K** positions. Cheap,
  deterministic, no oracle in the hot path (decision Q6).
- **D-Wave (pending, last).** Solves the *same* QUBO SA does, on the QPU via the
  Ocean SDK. Only the body is unimplemented; the `solve_qubo`/`QPU` contract is in
  place so it drops straight into the race once a Leap token is available.

## Key invariants

1. **`slider_map.py` is the only translator** of 0–100 sliders → physical params (γ, w_max, w_min, τ, K, λ_t). The frontend never sees physical params.
2. **`config.py` owns every static knob** — bankroll, bit precision, penalty weights, ε tolerances, K bounds.
3. **`basket.py` is the single source of the asset universe.**
4. **The MTM loop never enters the solver path** — pure revaluation until the next retune.
5. **One problem, two encodings** — MIQP (Gurobi) and QUBO (SA, D-Wave) minimize the same objective over the same feasible set (budget · box · exactly-K), so the race is meaningful.

## Critical paths

- **Build-and-solve hot path**: `EP3 → JOB → SM → (CE + RE) → QE → RTR → FEAS → QD → RT → AG/JOBS → response`. (`QD` decode applies to a QUBO winner — SA or D-Wave; a Gurobi MIQP winner returns weights directly.)
- **MTM hot loop**: `SCHED → PNL → AG/LB → BUS → EP5`.
- **First-solve vs retune branch lives in `RT` (retune.py)** — invisible to the solvers, which each see a fresh problem in their native form.
