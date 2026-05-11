// Mock implementations of the MVP API contract. Engineers replace this file
// (or swap the re-export in `api/index.ts`) with a real backend later. The
// rest of the app calls these via `api/index.ts`, not directly.

import type {
  AgentConfig,
  AgentUpdate,
  LeaderboardEntry,
  RoutingResult,
} from './types';

const STORAGE_PREFIX = 'quip:agents:';

const CLASSICAL_PROVIDERS = [
  { name: 'Helios-12',  meta: 'MILP baseline · 32 vCPU classical worker' },
  { name: 'Falcon-7',   meta: 'CP-SAT solver · 24 vCPU' },
  { name: 'Cumulus-3',  meta: 'Gurobi MIP · 16 vCPU' },
  { name: 'Atlas-9',    meta: 'Branch-and-bound · 48 vCPU' },
  { name: 'Nimbus-5',   meta: 'Simulated annealing · 32 vCPU' },
  { name: 'Stratos-2',  meta: 'OR-Tools · 24 vCPU' },
  { name: 'Cirrus-8',   meta: 'Tabu search · 16 vCPU' },
  { name: 'Boreas-4',   meta: 'Genetic solver · 32 vCPU' },
];

const TOP_10: LeaderboardEntry[] = [
  { rank: 1,  agentId: 'a01', name: 'Hilbert Spaceship',      handle: '@hilbertspaceship',    total: 11402, plUSD:  1402, plPct: 14.02, jobsSolved: 88, primaryProvider: 'QPU' },
  { rank: 2,  agentId: 'a02', name: 'Bra-Ket Boy',            handle: '@braketboy',           total: 10981, plUSD:   981, plPct:  9.81, jobsSolved: 73, primaryProvider: 'QPU' },
  { rank: 3,  agentId: 'a03', name: 'Eigenvalue Eve',         handle: '@eigenvalueeve',       total: 10778, plUSD:   778, plPct:  7.78, jobsSolved: 66, primaryProvider: 'QPU' },
  { rank: 4,  agentId: 'a04', name: 'Annealing Ant',          handle: '@annealingant',        total: 10612, plUSD:   612, plPct:  6.12, jobsSolved: 54, primaryProvider: 'QPU' },
  { rank: 5,  agentId: 'a05', name: 'QUBO McQuboface',        handle: '@qubomcquboface',      total: 10403, plUSD:   403, plPct:  4.03, jobsSolved: 48, primaryProvider: 'QPU' },
  { rank: 6,  agentId: 'a06', name: 'Lattice Theory',         handle: '@latticetheory',       total: 10142, plUSD:   142, plPct:  1.42, jobsSolved: 41, primaryProvider: 'QPU' },
  { rank: 7,  agentId: 'a07', name: 'Schrödinger’s Bag', handle: '@schrodingersbag',     total: 10089, plUSD:    89, plPct:  0.89, jobsSolved: 37, primaryProvider: 'CPU' },
  { rank: 8,  agentId: 'a08', name: 'Probably Approximately', handle: '@probablyapproximately', total: 10041, plUSD: 41, plPct: 0.41, jobsSolved: 33, primaryProvider: 'QPU' },
  { rank: 9,  agentId: 'a09', name: 'Coherent Cat',           handle: '@coherentcat',         total: 10029, plUSD:    29, plPct:  0.29, jobsSolved: 30, primaryProvider: 'QPU' },
  { rank: 10, agentId: 'a10', name: 'Tunneling Tina',         handle: '@tunnelingtina',       total:  9994, plUSD:    -6, plPct: -0.06, jobsSolved: 28, primaryProvider: 'CPU' },
];

// Synthetic AgentConfig for each seeded leaderboard entry so that demo URLs
// (e.g. /kiosk/welcome?agent=a06, /p/a06) render without needing the kiosk
// form to have created the agent in this browser's localStorage.
const SEEDED_AGENTS: Record<string, AgentConfig> = {
  a01: { name: 'Hilbert Spaceship',      handle: '@hilbertspaceship',      sliders: { tradingActivity: 95, riskPreference: 95, tradeSize: 85, holdingStyle: 10, diversification: 20 } },
  a02: { name: 'Bra-Ket Boy',            handle: '@braketboy',             sliders: { tradingActivity: 80, riskPreference: 85, tradeSize: 70, holdingStyle: 20, diversification: 30 } },
  a03: { name: 'Eigenvalue Eve',         handle: '@eigenvalueeve',         sliders: { tradingActivity: 65, riskPreference: 78, tradeSize: 60, holdingStyle: 35, diversification: 45 } },
  a04: { name: 'Annealing Ant',          handle: '@annealingant',          sliders: { tradingActivity: 55, riskPreference: 70, tradeSize: 50, holdingStyle: 45, diversification: 55 } },
  a05: { name: 'QUBO McQuboface',        handle: '@qubomcquboface',        sliders: { tradingActivity: 70, riskPreference: 60, tradeSize: 65, holdingStyle: 40, diversification: 50 } },
  a06: { name: 'Lattice Theory',         handle: '@latticetheory',         sliders: { tradingActivity: 70, riskPreference: 78, tradeSize: 50, holdingStyle: 30, diversification: 55 } },
  a07: { name: 'Schrödinger’s Bag', handle: '@schrodingersbag',       sliders: { tradingActivity: 40, riskPreference: 50, tradeSize: 40, holdingStyle: 60, diversification: 65 } },
  a08: { name: 'Probably Approximately', handle: '@probablyapproximately', sliders: { tradingActivity: 50, riskPreference: 55, tradeSize: 45, holdingStyle: 55, diversification: 70 } },
  a09: { name: 'Coherent Cat',           handle: '@coherentcat',           sliders: { tradingActivity: 35, riskPreference: 45, tradeSize: 40, holdingStyle: 70, diversification: 60 } },
  a10: { name: 'Tunneling Tina',         handle: '@tunnelingtina',         sliders: { tradingActivity: 25, riskPreference: 30, tradeSize: 30, holdingStyle: 80, diversification: 75 } },
};

function uuid(): string {
  return 'a' + Math.random().toString(36).slice(2, 10);
}

function delay<T>(value: T, ms = 250 + Math.random() * 350): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(value), ms));
}

export async function submitAgent(config: AgentConfig): Promise<{ agentId: string; qrUrl: string }> {
  const agentId = uuid();
  const qrUrl = `${window.location.origin}/p/${agentId}`;
  localStorage.setItem(STORAGE_PREFIX + agentId, JSON.stringify({ ...config, agentId, createdAt: Date.now() }));
  return delay({ agentId, qrUrl });
}

export async function getAgent(agentId: string): Promise<AgentConfig | null> {
  const raw = localStorage.getItem(STORAGE_PREFIX + agentId);
  if (raw) {
    try { return JSON.parse(raw); } catch { /* fall through to seeded */ }
  }
  return SEEDED_AGENTS[agentId] ?? null;
}

export async function requestOptimization(_agentId: string): Promise<RoutingResult> {
  const isQuantum = Math.random() < 0.8;
  if (isQuantum) {
    const qpu = 0.25 + Math.random() * 0.6;          // 0.25–0.85s
    const classical = 3.5 + Math.random() * 4.5;     // 3.5–8s
    return delay({
      provider: 'D-Wave Advantage',
      providerType: 'QPU' as const,
      solveTime: qpu,
      vsClassical: Math.round((classical / qpu) * 10) / 10,
      portfolio: defaultPortfolio(),
    });
  }
  const c = CLASSICAL_PROVIDERS[Math.floor(Math.random() * CLASSICAL_PROVIDERS.length)];
  const cpu = 1.6 + Math.random() * 1.0;
  const qpu = Math.max(0.4, cpu - 0.4 - Math.random() * 0.3);
  return delay({
    provider: c.name,
    providerType: 'CPU' as const,
    solveTime: cpu,
    vsClassical: Math.round((qpu / cpu) * 10) / 10,
    portfolio: defaultPortfolio(),
  });
}

export async function getLeaderboard(): Promise<LeaderboardEntry[]> {
  return delay(TOP_10);
}

export function subscribeAgent(agentId: string, callback: (update: AgentUpdate) => void): () => void {
  const baseTotal = (TOP_10.find(a => a.agentId === agentId)?.total) ?? 10000;
  let total = baseTotal;
  const interval = setInterval(() => {
    const drift = (Math.random() - 0.45) * 8;       // slight upward bias
    total = Math.max(9000, Math.min(15000, total + drift));
    const plUSD = Math.round((total - 10000));
    const plPct = Math.round((plUSD / 10000) * 10000) / 100;
    callback({ plUSD, plPct, total: Math.round(total) });
  }, 3000);
  return () => clearInterval(interval);
}

function defaultPortfolio() {
  return [
    { ticker: 'BTC' as const,  pct: 42, usd: 4200 },
    { ticker: 'ETH' as const,  pct: 28, usd: 2800 },
    { ticker: 'SOL' as const,  pct: 22, usd: 2200 },
    { ticker: 'USDC' as const, pct: 8,  usd:  800 },
  ];
}
