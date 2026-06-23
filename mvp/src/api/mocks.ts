// Mock implementations of the MVP API contract. Engineers replace this file
// (or swap the re-export in `api/index.ts`) with a real backend later. The
// rest of the app calls these via `api/index.ts`, not directly.

import type {
  AgentConfig,
  AgentUpdate,
  AssetTicker,
  LeaderboardEntry,
  OptimizePatch,
  PortfolioEntry,
  RoutingResult,
  RoutingStats,
  SolverResult,
  SubmitAgentResponse,
  SubscribeOptions,
  TvEvent,
  ValuationHistoryPoint,
} from './types';
import { ASSET_BY_TICKER } from './assets';
import { rebalanceEveryHours } from '../utils/strategy';
import { deriveUnits, driftSpot, markToMarket, SIM_BASE_SPOT, type Spot } from '../utils/mtm';

const BANKROLL = 10000;

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
  a01: { name: 'Hilbert Spaceship',      handle: '@hilbertspaceship',      sliders: { rebalanceFrequency: 95, riskPreference: 95, maxPositionSize: 85 } },
  a02: { name: 'Bra-Ket Boy',            handle: '@braketboy',             sliders: { rebalanceFrequency: 80, riskPreference: 85, maxPositionSize: 70 } },
  a03: { name: 'Eigenvalue Eve',         handle: '@eigenvalueeve',         sliders: { rebalanceFrequency: 65, riskPreference: 78, maxPositionSize: 60 },
         assets: ['XRP', 'ALGO', 'IONQ', 'IBM', 'SAF', 'ARQQ'] },
  a04: { name: 'Annealing Ant',          handle: '@annealingant',          sliders: { rebalanceFrequency: 55, riskPreference: 70, maxPositionSize: 50 } },
  a05: { name: 'QUBO McQuboface',        handle: '@qubomcquboface',        sliders: { rebalanceFrequency: 70, riskPreference: 60, maxPositionSize: 65 } },
  // a06 selects the ENTIRE 28-asset universe — the worst-case portfolio demo.
  a06: { name: 'Lattice Theory',         handle: '@latticetheory',         sliders: { rebalanceFrequency: 70, riskPreference: 78, maxPositionSize: 50 },
         assets: ['BTC', 'ETH', 'BNB', 'USDC', 'XRP', 'SOL', 'HYPE', 'DOGE', 'USDT', 'ZEC', 'ALGO', 'STRK', 'FIL', 'RENDER',
                  'IONQ', 'QBTS', 'RGTI', 'QUBT', 'IBM', 'SAF', 'SPCX', 'HON', 'LAES', 'ARQQ', 'GOOGL', 'NVDA', 'MSFT', 'AMZN'] },
  a07: { name: 'Schrödinger’s Bag', handle: '@schrodingersbag',       sliders: { rebalanceFrequency: 40, riskPreference: 50, maxPositionSize: 40 } },
  a08: { name: 'Probably Approximately', handle: '@probablyapproximately', sliders: { rebalanceFrequency: 50, riskPreference: 55, maxPositionSize: 45 } },
  a09: { name: 'Coherent Cat',           handle: '@coherentcat',           sliders: { rebalanceFrequency: 35, riskPreference: 45, maxPositionSize: 40 } },
  a10: { name: 'Tunneling Tina',         handle: '@tunnelingtina',         sliders: { rebalanceFrequency: 25, riskPreference: 30, maxPositionSize: 30 } },
};

function uuid(): string {
  return 'a' + Math.random().toString(36).slice(2, 10);
}

function delay<T>(value: T, ms = 250 + Math.random() * 350): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(value), ms));
}

export async function submitAgent(config: AgentConfig): Promise<SubmitAgentResponse> {
  const agentId = uuid();
  const token = `mock-${agentId}`;  // mock has no real auth; mirror the real QR shape
  const qrUrl = `${window.location.origin}/p/${agentId}#t=${token}`;
  localStorage.setItem(STORAGE_PREFIX + agentId, JSON.stringify({ ...config, agentId, createdAt: Date.now() }));
  return delay({ agentId, qrUrl, token });
}

export async function getAgent(agentId: string): Promise<AgentConfig | null> {
  const raw = localStorage.getItem(STORAGE_PREFIX + agentId);
  if (raw) {
    try { return JSON.parse(raw); } catch { /* fall through to seeded */ }
  }
  return SEEDED_AGENTS[agentId] ?? null;
}

// Merge a patch into the stored agent (creating a localStorage copy of a
// seeded agent on first edit). Used by the phone profile's basket editor.
export async function updateAgent(agentId: string, patch: Partial<AgentConfig>): Promise<AgentConfig> {
  const current = (await getAgent(agentId)) ?? ({ name: 'Player', sliders: { rebalanceFrequency: 50, riskPreference: 50, maxPositionSize: 50 } } as AgentConfig);
  const next = { ...current, ...patch };
  localStorage.setItem(STORAGE_PREFIX + agentId, JSON.stringify({ ...next, agentId, createdAt: Date.now() }));
  return delay(next);
}

export async function requestOptimization(
  agentId: string,
  patch: OptimizePatch = {},
): Promise<RoutingResult> {
  if (patch.sliders || patch.assets) {
    await updateAgent(agentId, patch);
  }
  const agent = await getAgent(agentId);
  const portfolio = portfolioFor(
    agentId,
    agent?.assets,
    agent?.sliders.maxPositionSize ?? 50,
    agent?.sliders.riskPreference ?? 50,
  );
  const intervalHours = rebalanceEveryHours(agent?.sliders.rebalanceFrequency ?? 50);
  // intervalHours is null when the cadence is Off — no scheduled rebalance.
  const nextRebalanceAt =
    intervalHours == null ? null : new Date(Date.now() + intervalHours * 60 * 60 * 1000).toISOString();
  const isQuantum = Math.random() < 0.8;
  if (isQuantum) {
    const qpu = 0.25 + Math.random() * 0.6;          // 0.25–0.85s
    const classical = 3.5 + Math.random() * 4.5;     // 3.5–8s
    const solverResults: SolverResult[] = [
      {
        provider: 'D-Wave Advantage',
        providerType: 'QPU' as const,
        status: 'winner',
        feasible: true,
        solveTime: qpu,
        raceTime: qpu + 0.08,
      },
      {
        provider: 'Simulated Annealing',
        providerType: 'CPU' as const,
        status: 'feasible',
        feasible: true,
        solveTime: classical,
        raceTime: classical,
      },
    ];
    return delay({
      provider: 'D-Wave Advantage',
      providerType: 'QPU' as const,
      solveTime: qpu,
      vsClassical: Math.round((classical / qpu) * 10) / 10,
      portfolio,
      solverResults,
      nextRebalanceAt,
      rebalanceIntervalHours: intervalHours,
    });
  }
  const c = CLASSICAL_PROVIDERS[Math.floor(Math.random() * CLASSICAL_PROVIDERS.length)];
  const cpu = 1.6 + Math.random() * 1.0;
  const qpu = Math.max(0.4, cpu - 0.4 - Math.random() * 0.3);
  const solverResults: SolverResult[] = [
    {
      provider: c.name,
      providerType: 'CPU' as const,
      status: 'winner',
      feasible: true,
      solveTime: cpu,
      raceTime: cpu,
    },
    {
      provider: 'D-Wave Advantage',
      providerType: 'QPU' as const,
      status: 'infeasible',
      feasible: false,
      solveTime: qpu,
      raceTime: qpu + 0.35,
    },
  ];
  return delay({
    provider: c.name,
    providerType: 'CPU' as const,
    solveTime: cpu,
    vsClassical: Math.round((qpu / cpu) * 10) / 10,
    portfolio,
    solverResults,
    nextRebalanceAt,
    rebalanceIntervalHours: intervalHours,
  });
}

// Live leaderboard simulation: each poll nudges every agent's total by a small
// random walk (slight upward bias), re-sorts, and reassigns ranks — so the TV
// board visibly moves and occasionally reshuffles, mirroring the backend MTM.
let boardState: LeaderboardEntry[] | null = null;

function tickBoard(): LeaderboardEntry[] {
  if (!boardState) boardState = TOP_10.map(entry => ({ ...entry }));
  for (const entry of boardState) {
    const drift = (Math.random() - 0.48) * 14;       // slight upward bias
    const total = Math.max(9200, entry.total + drift);
    entry.total = total;
    entry.plUSD = Math.round(total - 10000);
    entry.plPct = Math.round((entry.plUSD / 10000) * 10000) / 100;
    if (Math.random() < 0.05) entry.jobsSolved += 1;
  }
  boardState.sort((a, b) => b.total - a.total);
  boardState.forEach((entry, i) => { entry.rank = i + 1; });
  return boardState.map(entry => ({ ...entry }));
}

export async function getLeaderboard(): Promise<LeaderboardEntry[]> {
  return delay(tickBoard(), 120);
}

// Live routing-stats simulation: a solve lands now and then; the QPU wins most.
const routingState = { total: 10, qpuWins: 8, cpuWins: 2 };

export async function getRoutingStats(): Promise<RoutingStats> {
  if (Math.random() < 0.35) {
    routingState.total += 1;
    if (Math.random() < 0.8) routingState.qpuWins += 1;
    else routingState.cpuWins += 1;
  }
  const { total, qpuWins, cpuWins } = routingState;
  const qpuPct = Math.round((qpuWins / total) * 100);
  const cpuPct = 100 - qpuPct;
  // Recent routings feed (newest first) — mostly QPU wins, the occasional CPU.
  const now = Date.now();
  const recent = Array.from({ length: 16 }, (_, i) => {
    const qpu = i % 6 !== 2;                       // ~1 in 6 is a CPU win
    const winSec = qpu ? 0.1 + Math.random() * 0.25 : 1.6 + Math.random();
    const vsSec = qpu
      ? 3.5 + Math.random() * 3.5
      : Math.max(0.4, winSec - 0.5 - Math.random() * 0.3);
    return {
      provider: qpu ? 'dwave' : 'sa',
      providerType: (qpu ? 'QPU' : 'CPU') as 'QPU' | 'CPU',
      solveTime: Math.round(winSec * 100) / 100,
      vsTime: Math.round(vsSec * 100) / 100,
      solvedAt: new Date(now - i * 47_000).toISOString(),
    };
  });
  return delay({
    total,
    qpuWins,
    cpuWins,
    qpuPct,
    cpuPct,
    providers: [
      { provider: 'dwave', providerType: 'QPU', count: qpuWins, pct: qpuPct },
      { provider: 'sa', providerType: 'CPU', count: cpuWins, pct: cpuPct },
    ],
    recent,
  });
}

export async function getValuationHistory(
  agentId: string,
  limit = 60,
): Promise<ValuationHistoryPoint[]> {
  const agent = TOP_10.find(row => row.agentId === agentId);
  if (!agent) {
    return delay([
      {
        total: 10000,
        plUSD: 0,
        plPct: 0,
        asOf: new Date().toISOString(),
        stale: false,
      },
    ], 120);
  }
  const finalTotal = agent?.total ?? 10000;
  const count = Math.max(2, Math.min(limit, 32));
  const seed = [...agentId].reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const startedAt = Date.now() - (count - 1) * 60_000;
  const points = Array.from({ length: count }, (_, i) => {
    const t = count === 1 ? 1 : i / (count - 1);
    const wiggle = Math.sin(seed + i * 1.7) * 22 * (1 - Math.abs(t - 0.5));
    const total = 10000 + (finalTotal - 10000) * t + wiggle;
    const plUSD = total - 10000;
    return {
      total,
      plUSD,
      plPct: plUSD / 100,
      asOf: new Date(startedAt + i * 60_000).toISOString(),
      stale: false,
    };
  });
  return delay(points, 120);
}

// Seeded per-agent/ticker offset so each demo agent opens with a distinct,
// stable starting P&L (units are derived at the flat base; the live spot then
// opens already nudged). Deterministic — the same agent renders the same open.
function seededOffset(agentId: string, ticker: string): number {
  let h = 2166136261;
  const s = `${agentId}:${ticker}`;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unit = ((h >>> 0) % 1000) / 1000;   // [0, 1)
  return (unit * 2 - 1) * 0.03;             // ±3% opening drift
}

// Mock live feed — mirrors the backend mark-to-market loop. Builds the agent's
// portfolio (the same allocation the optimize call returns), fixes token units,
// then drifts each spot by a small vol-scaled random walk every tick and emits
// the full holdings array so the allocation bar, per-holding rows, total, and
// sparkline all move offline exactly as they would against the live backend.
export function subscribeAgent(
  agentId: string,
  callback: (update: AgentUpdate) => void,
  options: SubscribeOptions = {},
): () => void {
  options.onStatus?.('connecting');
  let cancelled = false;
  let timer: ReturnType<typeof setInterval> | null = null;

  (async () => {
    const agent = await getAgent(agentId);
    if (cancelled) return;
    const portfolio = portfolioFor(
      agentId,
      agent?.assets,
      agent?.sliders.maxPositionSize ?? 50,
      agent?.sliders.riskPreference ?? 50,
    );
    const baseSpot: Spot = {};
    for (const entry of portfolio) baseSpot[entry.ticker] = SIM_BASE_SPOT;
    const units = deriveUnits(
      portfolio.map(entry => ({ ticker: entry.ticker, usd: entry.usd })),
      baseSpot,
    );
    const spot: Spot = {};
    const vol: Record<string, number> = {};
    for (const entry of portfolio) {
      spot[entry.ticker] = SIM_BASE_SPOT * (1 + seededOffset(agentId, entry.ticker));
      vol[entry.ticker] = ASSET_BY_TICKER[entry.ticker]?.vol ?? 0.3;
    }

    const emit = () => {
      const m = markToMarket(units, spot, BANKROLL);
      callback({
        plUSD: m.plUSD,
        plPct: m.plPct,
        total: m.total,
        asOf: new Date().toISOString(),
        stale: false,
        holdings: m.holdings,
      });
    };

    options.onStatus?.('live');
    emit();
    timer = setInterval(() => {
      if (cancelled) return;
      for (const ticker of Object.keys(spot)) {
        spot[ticker] = driftSpot(spot[ticker], vol[ticker], Math.random);
      }
      emit();
    }, 1500);
  })();

  return () => {
    cancelled = true;
    if (timer) clearInterval(timer);
    options.onStatus?.('closed');
  };
}

// Synthetic booth-wide TV events. Emits a new-agent "interrupt" on a timer so
// the State D welcome is demonstrable offline — the real backend publishes the
// same shape on /tv/events when an agent's first solve lands (orchestration/job.py).
const DEMO_NEW_AGENTS = ['Coherent Carla', 'Tunneling Theo', 'Qubit Quokka', 'Bra-Ket Bo', 'Eigen Ada', 'Annealing Ana'];

export function subscribeTvEvents(
  callback: (event: TvEvent) => void,
  options: SubscribeOptions = {},
): () => void {
  options.onStatus?.('live');
  let i = 0;
  const timer = setInterval(() => {
    const name = DEMO_NEW_AGENTS[i % DEMO_NEW_AGENTS.length];
    i += 1;
    callback({ type: 'new-agent', agentId: `demo-${i}`, name });
  }, 25_000);
  return () => {
    clearInterval(timer);
    options.onStatus?.('closed');
  };
}

// Builds the optimizer's "answer" from the agent's selected basket. EVERY
// selected asset gets an allocation (a 28-asset basket yields 28 holdings),
// weighted by exponential decay over a deterministic per-agent ordering
// (same agent → same portfolio on re-render). Agents without a stored
// basket (older/seeded entries) fall back to the demo basket.
const FALLBACK_BASKET: AssetTicker[] = ['BTC', 'ETH', 'SOL', 'USDC'];

function portfolioFor(agentId: string, assets?: AssetTicker[], maxPositionSize = 50, riskPreference = 50): PortfolioEntry[] {
  const basket = assets && assets.length ? assets : FALLBACK_BASKET;
  // Risk preference tilts WHICH assets lead the allocation (γ on the
  // covariance term in the real solver): conservative agents lead with
  // low-volatility assets (stablecoins, large caps), aggressive agents
  // lead with high-volatility ones (small-cap quantum stocks, memecoins).
  // A name-seeded jitter keeps different agents distinct.
  let h = 0;
  for (let i = 0; i < agentId.length; i++) h = (h * 31 + agentId.charCodeAt(i)) >>> 0;
  const rank = (t: string) => {
    let r = h;
    for (let i = 0; i < t.length; i++) r = (r * 33 + t.charCodeAt(i)) >>> 0;
    return r;
  };
  const r01 = riskPreference / 100;
  const score = (t: AssetTicker) => {
    const vol = ASSET_BY_TICKER[t].vol;
    return (1 - r01) * (1 - vol) + r01 * vol + 0.15 * ((rank(t) % 1000) / 1000);
  };
  const ordered = [...basket].sort((a, b) => score(b) - score(a));
  // Exponential decay, normalized. The position-size slider drives the
  // optimizer's concentration appetite (like risk interacting with the cap
  // in the real solver): Tiny → near-equal weights, Heavy → steep decay
  // into the top holdings. The cap below then enforces the hard bound.
  const s = maxPositionSize / 100;
  const decay = ordered.length > 10
    ? 0.99 - s * 0.19    // 28 assets: top ≈ 3.6% (Tiny) … ≈ 20% (Heavy)
    : 0.95 - s * 0.30;   // small baskets: near-equal … strongly concentrated
  const raw = ordered.map((_, i) => Math.pow(decay, i));
  const total = raw.reduce((a, b) => a + b, 0);
  let w = raw.map(v => v / total);

  // Apply the per-asset cap (relative to basket size — see strategy.ts
  // maxPositionCapPct): clamp and water-fill the excess onto uncapped
  // holdings until everything respects the cap.
  const n = ordered.length;
  const floor = 1 / n;
  const cap = floor + (maxPositionSize / 100) * (Math.max(0.5, floor) - floor);
  for (let pass = 0; pass < 10; pass++) {
    const excess = w.reduce((a, v) => a + Math.max(0, v - cap), 0);
    if (excess < 1e-6) break;
    const uncappedSum = w.reduce((a, v) => a + (v < cap ? v : 0), 0);
    w = w.map(v => v >= cap ? cap : v + (uncappedSum > 0 ? (v / uncappedSum) * excess : 0));
  }

  let pctLeft = 100;
  return ordered.map((ticker, i) => {
    const pct = i === ordered.length - 1
      ? Math.round(pctLeft * 10) / 10
      : Math.round(w[i] * 1000) / 10;
    pctLeft -= pct;
    return { ticker, pct, usd: Math.round(pct * 100) };
  });
}
