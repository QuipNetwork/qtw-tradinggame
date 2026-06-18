// API contract for the Quip Network QTW 2026 trading-competition MVP.
// Engineers wire a real backend by implementing these signatures (see api/index.ts).

// Three strategy sliders, all native to the portfolio-allocation problem the
// solver actually runs (the optimizer allocates — it doesn't execute trades):
// rebalanceFrequency = how often the agent dispatches a re-optimization job;
// riskPreference     = risk-aversion term in the objective;
// maxPositionSize    = per-asset weight cap.
// (Holding style and diversification were dropped — the basket expresses those.)
export type SliderValues = {
  rebalanceFrequency: number;  // 0–100
  riskPreference: number;      // 0–100
  maxPositionSize: number;     // 0–100
};

export type AgentConfig = {
  name: string;
  handle?: string;              // display handle, auto-derived from the player name
  email?: string;               // required at sign-up; optional here for seeded demo agents
  reachOut?: string[];          // optional, multi-select — "Would you like someone from our team to reach out to you?" (verbatim Luma event options). Captures consent + intent + segment in one; "No thanks" = opt out.
  updatesOptIn?: boolean;       // "Sign me up for updates from Quip Network" — general newsletter opt-in, separate from the direct reach-out request
  sliders: SliderValues;
  assets?: AssetTicker[];       // the player's selected basket (subset of the 28-asset universe)
  lastSolvedAt?: string | null;
  nextRebalanceAt?: string | null;
  rebalanceIntervalHours?: number | null;
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

export type AgentUpdate = {
  plUSD: number;
  plPct: number;
  total: number;
  asOf?: string | null;
  stale?: boolean;
  holdings?: HoldingUpdate[];
  nextRebalanceAt?: string | null;
  rebalanceIntervalHours?: number | null;
};
