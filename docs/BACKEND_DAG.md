# Backend DAG — System dataflow

Full dataflow for the QTW 2026 Trading Game backend, from frontend touch through
solver race back to live MTM updates. Solid arrows = synchronous data flow;
dotted arrows = reads from persistence or external data.

**Legend.** Blue = persistence stores; purple = solvers; the amber external is
the **assets-api service** (real prices; a deterministic synthetic source is the
default until it's enabled in config). The D-Wave provider is implemented and
joins the race when `DWAVE_API_TOKEN` is set. The frontend MVP runs on **mocks**
until it's wired to the real API.

**What's left, in order:** ① real-data shakeout (assets-api) → ② frontend wiring → ③ scheduled rebalances + QPU budget.

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
        SM["slider_map.py<br/>0-100 → γ,w_max,w_min,cadence"]
        CE["estimators/covariance.py<br/>Σ from 720h window"]
        RE["estimators/expected_return.py<br/>μ from fixed 168h window"]
        QE["qubo_encoder.py<br/>QP → bit-discretized QUBO"]
        QD["qubo_decoder.py<br/>bitstring → weights"]
        RT["allocate<br/>liquidate → reallocate"]
        PNL["pnl.py<br/>holdings × spot → AgentUpdate"]
        BASKET["basket.py<br/>25-asset universe"]
    end

    %% ===== Market data =====
    subgraph DATA["Market data"]
        SRC["prices/source<br/>synthetic | assets-api"]
        ASSETSAPI[/"assets-api service<br/>Alpaca · Massive · CoinGecko"/]
    end

    %% ===== Solvers =====
    subgraph SOLV["Solvers (race · first feasible wins)"]
        RTR["router.py<br/>parallel dispatch (ThreadPoolExecutor)"]
        GU["providers/gurobi.py<br/>continuous QP<br/>CPU role + offline oracle"]
        SA["providers/sa.py<br/>QUBO via neal<br/>CPU role"]
        DW["providers/dwave.py<br/>QUBO on Advantage QPU<br/>joins race with DWAVE_API_TOKEN"]
        FEAS["feasibility.py<br/>budget · box check"]
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
    CFG["config.py<br/>bankroll · ε · b · basket min"]

    %% ===== Frontend → API =====
    K -->|"submitAgent(config)"| EP1
    K -->|"requestOptimization(id)"| EP3
    P -->|"retune w/ sliders + basket"| EP3
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
    SM -->|"γ, w_max, w_min"| QE
    BASKET --> RE
    BASKET --> CE
    SRC --> RE
    SRC --> CE
    CE -->|"Σ (n×n)"| QE
    RE -->|"μ (n)"| QE
    CFG -.->|"b, λ_sum, λ_K"| QE

    QE -->|"QP (Gurobi) · QUBO (SA, D-Wave)"| RTR
    RTR -->|"continuous QP"| GU
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

    %% ===== Real data path =====
    ASSETSAPI -.->|"/v1/history · /v1/spot"| SRC

    %% ===== Styling =====
    classDef external fill:#fff4e6,stroke:#cc8800,color:#5c3d00
    classDef storage fill:#e6f2ff,stroke:#0066cc,color:#0d2b52
    classDef solver fill:#f0e6ff,stroke:#6600cc,color:#2a0a52

    class AG,JOBS,LB storage
    class DW,SA,GU solver
    class ASSETSAPI external
```

## Reading the DAG

- **Top → bottom = user request flow**: frontend kiosk/phone touch → API → orchestration job → financial pipeline → solver race → decode → persist → respond.
- **Bottom = MTM background loop**: the scheduler ticks the PnL module every few seconds, revalues holdings against the current spot, updates persistence, and pushes deltas over WS.
- **Dotted arrows = reads** (from persistence or external data); solid arrows = synchronous data flow.
- **Data layer**: the estimators and PnL read through `prices/source` — deterministic synthetic by default, the assets-api service when enabled in config. Same interface, no pipeline change.
- **Three solver paths converge at `feasibility.py`** — first feasible wins. Gurobi additionally serves as the offline oracle (separate from the race).

## Solver race — how it connects

One canonical problem fans out to the solvers in two encodings — the continuous
QP for Gurobi, the bit-discretized QUBO for SA and D-Wave — and the **first
feasible** answer wins.

- **The canonical problem.** `orchestration/job.py` assembles a `PortfolioProblem`
  (`financial/types.py`) over the player's basket from the slider params and the
  estimates (μ, Σ). Every solve is a fresh allocation — a retune liquidates and
  reallocates, so there is no turnover anchor; no cardinality constraint either,
  the basket decides participation and a min-position floor keeps every selected
  asset held.
- **The router** (`solvers/router.py::race`) encodes the QUBO once, hashes it for
  the audit log, and dispatches the providers concurrently on a thread pool (the
  solve work releases the GIL). It takes the first feasible result and keeps the
  runner-up for the `vsClassical` baseline (decision Q7).
- **Encodings.** Gurobi solves the QP natively; SA and D-Wave solve the QUBO and
  decode the winning bitstring (`qubo_decoder.py`, simplex-normalized to absorb
  bit-grid error). Gurobi is also the offline oracle for penalty calibration.
- **Feasibility gate** (`solvers/feasibility.py`) is identical for all three —
  budget `|Σwᵢ−1| < ε`, box `w_min ≤ wᵢ ≤ w_max`. Cheap, deterministic, no
  oracle in the hot path (decision Q6).
- **D-Wave.** Solves the *same* QUBO SA does, on Advantage via the Ocean SDK.
  Joins the race only when `DWAVE_API_TOKEN` is set (QPU time costs money); its
  reported solve time is QPU access time, not wall clock.

## Key invariants

1. **`slider_map.py` is the only translator** of 0–100 sliders → physical params (γ, w_max, w_min, τ, K, λ_t). The frontend never sees physical params.
2. **`config.py` owns every static knob** — bankroll, bit precision, penalty weights, ε tolerances, K bounds.
3. **`basket.py` is the single source of the asset universe.**
4. **The MTM loop never enters the solver path** — pure revaluation until the next retune.
5. **One problem, two encodings** — QP (Gurobi) and QUBO (SA, D-Wave) minimize the same objective over the same feasible set (budget · box), so the race is meaningful.

## Critical paths

- **Build-and-solve hot path**: `EP3 → JOB → SM → (CE + RE) → QE → RTR → FEAS → QD → RT → AG/JOBS → response`. (`QD` decode applies to a QUBO winner — SA or D-Wave; a Gurobi QP winner returns weights directly.)
- **MTM hot loop**: `SCHED → PNL → AG/LB → BUS → EP5`.
- **First solve and retune are the same math** — a retune liquidates at spot and reallocates over the (possibly re-selected) basket; the solvers always see a fresh problem.
