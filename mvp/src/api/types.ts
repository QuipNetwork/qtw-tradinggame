// API contract for the Quip Network QTW 2026 trading-competition MVP.
// Engineers wire a real backend by implementing these signatures (see api/index.ts).

// Strategy controls for the portfolio-allocation problem the solver runs (the
// optimizer allocates — it doesn't execute trades):
// rebalanceFrequency = how often the agent dispatches a re-optimization job
//                      (discrete tiers: Daily / 8h / 4h / 2h / Hourly);
// riskPreference     = risk-aversion term in the objective;
// maxPositionSize    = per-asset weight cap;
// holdCount          = Method 3: how many of the basket the optimizer holds (K).
//                      Absolute count in [2, basket size]; omitted ⇒ hold all.
export type SliderValues = {
  rebalanceFrequency: number;  // 0–100 (snaps to 5 cadence tiers)
  riskPreference: number;      // 0–100
  maxPositionSize: number;     // 0–100
  holdCount?: number;          // 2..basketSize; the cardinality K (Method 3)
};

export type AgentConfig = {
  name: string;
  handle?: string;              // display handle, auto-derived from the player name
  email?: string;               // required at sign-up; optional here for seeded demo agents
  reachOut?: string[];          // optional, multi-select — "Would you like someone from our team to reach out to you?" (verbatim Luma event options). Captures consent + intent + segment in one; "No thanks" = opt out.
  updatesOptIn?: boolean;       // "Email me my portfolio results" — opt-in to performance update emails
  updateFrequency?: 'daily' | 'hourly';  // cadence for the result emails (only meaningful when updatesOptIn); default 'daily'
  sliders: SliderValues;
  assets?: AssetTicker[];       // the player's selected basket (subset of the 28-asset universe)
  lastSolvedAt?: string | null;
  nextRebalanceAt?: string | null;
  rebalanceIntervalHours?: number | null;
  qpuBudget?: QpuBudgetStatus | null;
};

export type SubmitAgentResponse = {
  agentId: string;
  qrUrl: string;
  bankroll?: number;
};

export type OptimizePatch = {
  sliders?: SliderValues;
  assets?: AssetTicker[];
};

export type ProviderType = 'QPU' | 'CPU';

export type QpuBudgetStatus = {
  used: number;
  limit: number;
  windowSeconds: number;
  retryAfterSeconds: number;
  nextAvailableAt?: string | null;
};

export type AssetClass = 'crypto' | 'stock';

// The full 28-asset tradable universe: 14 crypto + 14 stocks.
export type AssetTicker =
  // crypto
  | 'BTC' | 'ETH' | 'BNB' | 'USDC' | 'XRP' | 'SOL' | 'HYPE'
  | 'DOGE' | 'USDT' | 'ZEC' | 'ALGO' | 'STRK' | 'FIL' | 'RENDER'
  // stocks
  | 'IONQ' | 'QBTS' | 'RGTI' | 'QUBT' | 'IBM' | 'SAF'
  | 'SPCX' | 'HON' | 'LAES' | 'ARQQ' | 'GOOGL'
  | 'NVDA' | 'MSFT' | 'AMZN';

export type AssetInfo = {
  ticker: AssetTicker;
  name: string;
  class: AssetClass;
  icon: string;        // filename in shared-design/asset-icons/
  color: string;       // mark color, used in the allocation bar
  vol: number;         // placeholder volatility score 0..1 (drives the risk tilt in the demo)
};

export type PortfolioEntry = {
  ticker: AssetTicker;
  pct: number;     // 0–100, the portfolio weight
  usd: number;     // dollar allocation
};

export type HoldingUpdate = {
  ticker: AssetTicker;
  units: number;
  spot: number;
  usd: number;
  pct: number;
};

export type SolverStatus = 'winner' | 'feasible' | 'infeasible' | 'failed' | 'timeout';

export type SolverResult = {
  provider: string;
  providerType: ProviderType;
  status: SolverStatus;
  feasible: boolean;
  solveTime: number | null;
  raceTime: number | null;      // audit/debug only; UI ranks by solveTime
  objective?: number | null;
  bestObjective?: boolean;      // quality leader (lowest objective); may differ from winner
  error?: string | null;
};

export type RoutingResult = {
  provider: string;             // e.g. 'D-Wave Advantage' or 'Helios-12'
  providerType: ProviderType;
  solveTime: number;            // seconds, e.g. 0.42
  vsClassical: number;          // legacy multiplier; UI uses solverResults
  portfolio: PortfolioEntry[];
  solverResults?: SolverResult[];
  kind?: 'first' | 'retune';
  jobId?: string | null;
  solvedAt?: string | null;
  nextRebalanceAt?: string | null;
  rebalanceIntervalHours?: number | null;
  qpuBudget?: QpuBudgetStatus | null;
};

export type LeaderboardEntry = {
  rank: number;
  agentId: string;
  name: string;
  handle: string | null;
  total: number;                // $11,402
  plUSD: number;                // +142
  plPct: number;                // +1.42
  jobsSolved: number;
  primaryProvider: ProviderType;
};

export type ValuationHistoryPoint = {
  total: number;
  plUSD: number;
  plPct: number;
  asOf?: string | null;
  stale?: boolean;
};

export type RoutingProviderStat = {
  provider: string;
  providerType: ProviderType;
  count: number;
  pct: number;
};

// One solved routing for the TV "recent routings" feed (newest first).
export type RecentRouting = {
  provider: string;             // raw key: 'dwave' | 'sa' | 'gurobi'
  providerType: ProviderType;   // 'QPU' | 'CPU'
  solveTime: number;            // winner seconds
  vsTime: number | null;        // runner-up seconds (null if unavailable)
  solvedAt: string;             // ISO-8601 UTC
};

export type RoutingStats = {
  total: number;
  qpuWins: number;
  cpuWins: number;
  qpuPct: number;
  cpuPct: number;
  providers: RoutingProviderStat[];
  recent: RecentRouting[];
};

export type AgentUpdate = {
  plUSD: number;
  plPct: number;
  total: number;
  asOf?: string | null;
  stale?: boolean;
  holdings?: HoldingUpdate[];
  nextRebalanceAt?: string | null;
  rebalanceIntervalHours?: number | null;
  qpuBudget?: QpuBudgetStatus | null;
};
