// API contract for the Quip Network QTW 2026 trading-competition MVP.
// Engineers wire a real backend by implementing these signatures (see api/index.ts).

export type SliderValues = {
  tradingActivity: number;    // 0–100
  riskPreference: number;
  tradeSize: number;
  holdingStyle: number;
  diversification: number;
};

export type AgentConfig = {
  name: string;
  handle?: string;
  sliders: SliderValues;
  assets?: AssetTicker[];       // the player's selected basket (subset of the 25-asset universe)
};

export type ProviderType = 'QPU' | 'CPU';

export type AssetClass = 'crypto' | 'stock';

// The full 25-asset tradable universe: 14 crypto + 11 stocks.
export type AssetTicker =
  // crypto
  | 'BTC' | 'ETH' | 'BNB' | 'USDC' | 'XRP' | 'SOL' | 'HYPE'
  | 'DOGE' | 'USDT' | 'ZEC' | 'ALGO' | 'STRK' | 'FIL' | 'RENDER'
  // stocks
  | 'IONQ' | 'QBTS' | 'RGTI' | 'QUBT' | 'QNT' | 'SAF'
  | 'INDI' | 'BTQ' | 'LAES' | 'ARQQ' | 'SPCX';

export type AssetInfo = {
  ticker: AssetTicker;
  name: string;
  class: AssetClass;
};

export type PortfolioEntry = {
  ticker: AssetTicker;
  pct: number;     // 0–100, the portfolio weight
  usd: number;     // dollar allocation
};

export type RoutingResult = {
  provider: string;             // e.g. 'D-Wave Advantage' or 'Helios-12'
  providerType: ProviderType;
  solveTime: number;            // seconds, e.g. 0.42
  vsClassical: number;          // multiplier, e.g. 14 (means 14× faster than classical)
  portfolio: PortfolioEntry[];
};

export type LeaderboardEntry = {
  rank: number;
  agentId: string;
  name: string;
  handle: string;
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
};
