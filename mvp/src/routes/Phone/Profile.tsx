import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import type {
  AgentConfig,
  AgentUpdate,
  RoutingResult,
  LeaderboardEntry,
  SliderValues,
  AssetTicker,
  AssetInfo,
  QpuBudgetStatus,
} from '../../api';
import { getAgent, getLeaderboard, requestOptimization, subscribeAgent, updateAgent, ASSETS, CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc } from '../../api';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';
import { solverRaceComparison, solverRaceRows } from '../../utils/solverRace';
import { glyphParams, labelFor, slidersToArray } from '../../utils/strategy';

const SLIDER_DEFS: Array<{ key: keyof SliderValues; label: string }> = [
  { key: 'rebalanceFrequency', label: 'Rebalance frequency' },
  { key: 'riskPreference',     label: 'Risk preference' },
  { key: 'maxPositionSize',    label: 'Max position size' },
];

// A basket needs at least this many assets (mirrors the kiosk sign-up rule).
const MIN_ASSETS = 3;
const WHOLE_USD = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
type RankInfo = { rank: number | null; total: number };

function formatRebalanceCountdown(nextRebalanceAt?: string | null, nowMs: number = Date.now()): string {
  if (!nextRebalanceAt) return 'Pending';
  const targetMs = Date.parse(nextRebalanceAt);
  if (!Number.isFinite(targetMs)) return 'Pending';
  const remaining = Math.max(0, targetMs - nowMs);
  if (remaining <= 0) return 'Due now';
  const totalSeconds = Math.ceil(remaining / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

function formatMinuteSecondCountdown(remainingMs: number): string {
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function roundedPnL(plUSD: number, plPct: number): {
  sign: '+' | '−' | '';
  tone: 'up' | 'down' | 'flat';
  usd: number;
  pct: string;
} {
  const roundedUsd = Math.round(plUSD);
  const roundedPct = Math.round(plPct * 100) / 100;
  if (roundedUsd === 0 && roundedPct === 0) {
    return { sign: '', tone: 'flat', usd: 0, pct: '0.00' };
  }
  const positive = roundedUsd > 0 || roundedPct > 0;
  return {
    sign: positive ? '+' : '−',
    tone: positive ? 'up' : 'down',
    usd: Math.abs(roundedUsd),
    pct: Math.abs(roundedPct).toFixed(2),
  };
}

function qpuCooldownTargetMs(budget?: QpuBudgetStatus | null): number | null {
  if (!budget?.nextAvailableAt) return null;
  const targetMs = Date.parse(budget.nextAvailableAt);
  return Number.isFinite(targetMs) ? targetMs : null;
}

function qpuCooldownFromError(error: unknown): { message: string; targetMs: number | null } | null {
  if (!(error instanceof Error)) return null;
  const maybe = error as Error & {
    status?: number;
    retryAfterSeconds?: number;
    qpuBudget?: QpuBudgetStatus;
  };
  if (maybe.status !== 429 && typeof maybe.retryAfterSeconds !== 'number') return null;
  const budgetTargetMs = qpuCooldownTargetMs(maybe.qpuBudget);
  const retryTargetMs = typeof maybe.retryAfterSeconds === 'number'
    ? Date.now() + maybe.retryAfterSeconds * 1000
    : null;
  return {
    message: maybe.message || 'QPU solve limit reached',
    targetMs: budgetTargetMs ?? retryTargetMs,
  };
}

function rankInfoFor(agentId: string, leaderboard: LeaderboardEntry[]): RankInfo {
  const row = leaderboard.find(entry => entry.agentId === agentId);
  return {
    rank: row?.rank ?? null,
    total: leaderboard.length,
  };
}

function sparkPoints(values: number[]): string {
  const series = values.length >= 2 ? values : [10000, 10000];
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = Math.max(1, max - min);
  return series.map((value, i) => {
    const x = (i / Math.max(1, series.length - 1)) * 76;
    const y = 32 - ((value - min) / range) * 25;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

export default function PhoneProfile() {
  const { agentId } = useParams();
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [sliders, setSliders] = useState<number[] | null>(null);
  const [result, setResult] = useState<RoutingResult | null>(null);
  const [live, setLive] = useState<AgentUpdate | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<'profile' | 'basket'>('profile');
  const [basket, setBasket] = useState<Set<AssetTicker>>(new Set());
  const [savingBasket, setSavingBasket] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalHistory, setTotalHistory] = useState<number[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [qpuCooldownUntilMs, setQpuCooldownUntilMs] = useState<number | null>(null);
  const [rankInfo, setRankInfo] = useState<RankInfo | null>(null);
  const glyphRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!agentId) return;
    (async () => {
      const a = await getAgent(agentId);
      if (!a) return;
      setAgent(a);
      setSliders(slidersToArray(a.sliders));
      setBasket(new Set(a.assets ?? []));
      const targetMs = qpuCooldownTargetMs(a.qpuBudget);
      if (targetMs && targetMs > Date.now()) setQpuCooldownUntilMs(targetMs);

      const cachedRaw = sessionStorage.getItem('quip:lastResult:' + agentId);
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as RoutingResult;
          setResult(cached);
          const targetMs = qpuCooldownTargetMs(cached.qpuBudget);
          if (targetMs && targetMs > Date.now()) setQpuCooldownUntilMs(targetMs);
        } catch { /* ignore */ }
      }
    })();
  }, [agentId]);

  useEffect(() => {
    if (!agentId) return;
    const currentAgentId = agentId;
    let cancelled = false;
    async function refreshRank() {
      try {
        const board = await getLeaderboard();
        if (!cancelled) setRankInfo(rankInfoFor(currentAgentId, board));
      } catch {
        // Keep the last known rank if the leaderboard request misses a tick.
      }
    }
    refreshRank();
    const timer = window.setInterval(refreshRank, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [agentId]);

  useEffect(() => {
    if (!agentId) return;
    return subscribeAgent(agentId, update => {
      setLive(update);
      setTotalHistory(prev => [...prev, update.total].slice(-24));
      const targetMs = qpuCooldownTargetMs(update.qpuBudget);
      if (targetMs && targetMs > Date.now()) setQpuCooldownUntilMs(targetMs);
    });
  }, [agentId]);

  useEffect(() => {
    if (!agent || !glyphRef.current) return;
    const seed = strHash(agent.name);
    const style = pickStyle(seed);
    renderGlyph(glyphRef.current, Object.assign({
      seed,
      ...glyphParams(agent.sliders),
      cell: 3,
    }, style));
  }, [agent]);

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!qpuCooldownUntilMs || qpuCooldownUntilMs > nowMs) return;
    setQpuCooldownUntilMs(null);
    setError(prev => (prev === 'QPU solve limit reached' ? null : prev));
  }, [nowMs, qpuCooldownUntilMs]);

  if (!agentId) return <div style={{ padding: 40 }}>Missing agent.</div>;
  if (!agent || !sliders) return null;

  async function retune() {
    if (busy || !agentId || !sliders) return;
    setBusy(true);
    setError(null);
    const next: SliderValues = SLIDER_DEFS.reduce<SliderValues>((acc, def, i) => {
      acc[def.key] = sliders[i];
      return acc;
    }, {} as SliderValues);
    const assets = ASSETS.filter(a => basket.has(a.ticker)).map(a => a.ticker);
    try {
      const r = await requestOptimization(agentId, { sliders: next, assets });
      setAgent(prev => prev ? {
        ...prev,
        sliders: next,
        assets,
        nextRebalanceAt: r.nextRebalanceAt ?? prev.nextRebalanceAt,
        rebalanceIntervalHours: r.rebalanceIntervalHours ?? prev.rebalanceIntervalHours,
        qpuBudget: r.qpuBudget ?? prev.qpuBudget,
      } : prev);
      setResult(r);
      getLeaderboard()
        .then(board => setRankInfo(rankInfoFor(agentId, board)))
        .catch(() => {});
      const targetMs = qpuCooldownTargetMs(r.qpuBudget);
      if (targetMs && targetMs > Date.now()) setQpuCooldownUntilMs(targetMs);
      sessionStorage.setItem('quip:lastResult:' + agentId, JSON.stringify(r));
    } catch (err) {
      const cooldown = qpuCooldownFromError(err);
      if (cooldown) {
        if (cooldown.targetMs && cooldown.targetMs > Date.now()) {
          setQpuCooldownUntilMs(cooldown.targetMs);
        }
        setError('QPU solve limit reached');
      } else {
        setError(err instanceof Error ? err.message : 'Could not re-optimize. Check the backend connection.');
      }
    } finally {
      setBusy(false);
    }
  }

  function toggleBasket(ticker: AssetTicker) {
    setBasket(prev => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  // Save only persists the basket and returns to the profile. Re-optimizing is
  // a separate, explicit action from the main profile ("Re-optimize on Quip").
  async function saveBasket() {
    if (savingBasket || !agentId || basket.size < MIN_ASSETS) return;
    setSavingBasket(true);
    setError(null);
    const assets = ASSETS.filter(a => basket.has(a.ticker)).map(a => a.ticker);
    try {
      await updateAgent(agentId, { assets });
      setAgent(prev => prev ? { ...prev, assets } : prev);
      setView('profile');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the basket. Check the backend connection.');
    } finally {
      setSavingBasket(false);
    }
  }

  const basketTile = (a: AssetInfo) => {
    const on = basket.has(a.ticker);
    return (
      <button
        type="button"
        key={a.ticker}
        className={`v4m-tile ${a.class}${on ? ' on' : ''}`}
        aria-pressed={on}
        onClick={() => toggleBasket(a.ticker)}
      >
        <span className="v4m-tile-check" aria-hidden="true">✓</span>
        <img className="v4m-tile-icon" src={assetIconSrc(a.ticker)} alt="" loading="lazy" />
        <span className="v4m-tile-ticker">{a.ticker}</span>
        <span className="v4m-tile-name">{a.name}</span>
      </button>
    );
  };

  const total = live?.total ?? 10142;
  const plUSD = live?.plUSD ?? 142;
  const plPct = live?.plPct ?? 1.42;
  const pnl = roundedPnL(plUSD, plPct);
  const lineColor = pnl.tone === 'down' ? '#ff6467' : pnl.tone === 'up' ? '#0A832E' : '#71717b';
  const spark = sparkPoints(totalHistory);

  const solveTime = result?.solveTime ?? 0.42;
  const providerName = result?.provider ?? 'D-Wave Advantage';
  const raceRows = solverRaceRows(result);
  const raceComparison = solverRaceComparison(result);
  const nextRebalanceAt =
    live?.nextRebalanceAt ?? result?.nextRebalanceAt ?? agent.nextRebalanceAt;
  const rebalanceIntervalHours =
    live?.rebalanceIntervalHours ??
    result?.rebalanceIntervalHours ??
    agent.rebalanceIntervalHours;
  const rebalanceCountdown = formatRebalanceCountdown(nextRebalanceAt, nowMs);
  const budgetTargetMs =
    qpuCooldownUntilMs ??
    qpuCooldownTargetMs(live?.qpuBudget) ??
    qpuCooldownTargetMs(result?.qpuBudget) ??
    qpuCooldownTargetMs(agent.qpuBudget);
  const qpuCooldownRemainingMs = budgetTargetMs ? Math.max(0, budgetTargetMs - nowMs) : 0;
  const qpuCoolingDown = qpuCooldownRemainingMs > 0;
  const qpuCooldownLabel = formatMinuteSecondCountdown(qpuCooldownRemainingMs);
  const retuneDisabled = busy || qpuCoolingDown;
  const retuneButtonText = busy
    ? 'Retuning via Quip'
    : qpuCoolingDown
      ? `QPU cooldown · ${qpuCooldownLabel}`
      : 'Retune with Quip';
  const retuneHelper = qpuCoolingDown ? null : error;
  const rankText = rankInfo?.rank ? `#${rankInfo.rank}` : '—';
  const rankTotalText = rankInfo?.total ? `of ${rankInfo.total}` : 'rank pending';

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#0a0a10', padding: 16 }}>
      <div className="mockup-frame phone dark">
        <div className="screen">
          <div className="qs-v4-mock phone-v4">

            <div className="v4m-status">
              <span>9:41</span>
              <div className="v4m-status-icons">
                <span className="v4m-bars"><span></span><span></span><span></span><span></span></span>
                <span style={{ fontFamily: "'JetBrains Mono',ui-monospace,monospace", fontSize: '0.6rem', letterSpacing: '0.04em' }}>5G</span>
                <span className="v4m-battery"></span>
              </div>
            </div>

            {view === 'basket' ? (
            <div className="v4m-basket-screen">
              <div className="v4m-basket-head">
                <button type="button" className="v4m-basket-back" onClick={() => setView('profile')} aria-label="Back to profile">←</button>
                <span className="v4m-section-eyebrow">Edit basket</span>
                <span className={`v4m-basket-count${basket.size > 0 && basket.size < MIN_ASSETS ? ' under' : ''}`}>{basket.size}/{ASSETS.length} · min {MIN_ASSETS}</span>
              </div>
              <div className="v4m-basket-scroll">
                <div className="v4m-basket-group">Crypto · {CRYPTO_ASSETS.length}</div>
                <div className="v4m-basket-grid">{CRYPTO_ASSETS.map(basketTile)}</div>
                <div className="v4m-basket-group">Stocks · {STOCK_ASSETS.length}</div>
                <div className="v4m-basket-grid">{STOCK_ASSETS.map(basketTile)}</div>
              </div>
              <button className={`v4m-cta${savingBasket ? ' busy' : ''}`} onClick={saveBasket} disabled={savingBasket || basket.size < MIN_ASSETS}>
                <span>{savingBasket ? 'Saving…' : 'Save basket'}</span>
                <span className="v4m-cta-arrow">→</span>
              </button>
              {(error || basket.size < MIN_ASSETS) && (
                <div className="v4m-cta-sub">{error ?? `Select at least ${MIN_ASSETS} assets`}</div>
              )}
            </div>
            ) : (
            <div className="v4m-phone-view">

            <div className="v4m-phone-head">
              <div>
                <div className="v4m-phone-name">{agent.name}</div>
              </div>
              <canvas ref={glyphRef} width={56} height={56}></canvas>
              <div className="v4m-phone-rank" style={{ gridColumn: '1 / 3', marginTop: 4, justifySelf: 'start' }}>
                <span>You're</span>
                <span className="v4m-rank-num">{rankText}</span>
                <span>{rankTotalText}</span>
              </div>
            </div>

            <div className="v4m-pl">
              <div>
                <div className="v4m-section-eyebrow">Total · {live?.stale ? 'Last close' : 'Live'}</div>
                <div className="v4m-pl-num">${WHOLE_USD.format(total)}</div>
                <div className={`v4m-pl-change ${pnl.tone}`}>
                  {pnl.sign}${WHOLE_USD.format(pnl.usd)} · {pnl.sign}{pnl.pct}%
                </div>
              </div>
              <svg className="v4m-spark" viewBox="0 0 80 36" preserveAspectRatio="none" aria-hidden="true" style={{ color: lineColor }}>
                <polyline
                  points={spark}
                  fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                />
              </svg>
            </div>

            <div className="v4m-phone-mega">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span className="v4m-section-eyebrow cyan-dot cyan">Solved via Quip · 4m ago</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
                <div>
                  <div className="v4m-phone-mega-hero">{providerName}</div>
                  <div className="v4m-phone-mega-meta">
                    {raceComparison.summary}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: "Georgia, 'Times New Roman', serif", fontStyle: 'italic', fontSize: '1.6rem', letterSpacing: '-0.025em', color: '#0891B2', lineHeight: 1 }}>
                    {solveTime.toFixed(2)}s
                  </div>
                </div>
              </div>
              <div className="v4m-race-block" style={{ borderTop: '1px solid #ececef', paddingTop: 8 }}>
                {raceRows.map(row => (
                  <div className={`v4m-race-row${row.isWinner ? ' winner' : ''}${row.feasible ? '' : ' muted'}`} style={{ gridTemplateColumns: '122px 1fr 54px' }} key={`${row.provider}-${row.status}`}>
                    <span className={`v4m-race-label${row.isWinner ? ' q' : ''}`}>
                      {row.label}
                      <span className="v4m-race-detail">{row.detail}</span>
                    </span>
                    <div className="v4m-race-bar"><div className={`v4m-race-fill${row.isWinner ? ' q' : ''}`} style={{ width: `${row.barPct}%` }}></div></div>
                    <span className="v4m-race-time">{row.timeLabel}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="v4m-rebalance-card">
              <div>
                <div className="v4m-section-eyebrow">Next QPU rebalance</div>
                <div className="v4m-rebalance-sub">
                  {rebalanceIntervalHours ? `Every ${rebalanceIntervalHours}h cadence` : 'Starts after first solve'}
                </div>
              </div>
              <div className="v4m-rebalance-time">{rebalanceCountdown}</div>
            </div>

            <button type="button" className="v4m-basket-open" onClick={() => setView('basket')}>
              <span className="v4m-section-eyebrow">Your basket · {basket.size} asset{basket.size === 1 ? '' : 's'}</span>
              <span className="v4m-basket-open-cta">Edit →</span>
            </button>

            <div>
              <div className="v4m-section-eyebrow" style={{ marginBottom: 8 }}>Strategy · Drag to Retune</div>
              {SLIDER_DEFS.map((def, i) => (
                <div className="v4m-slider" key={def.key}>
                  <div className="v4m-slider-top">
                    <span className="v4m-slider-label">{def.label}</span>
                    <span className="v4m-slider-val">{labelFor(i, sliders[i])}</span>
                  </div>
                  <div className="v4m-slider-shell">
                    <div className="v4m-slider-track">
                      <div className="v4m-slider-fill" style={{ width: `${sliders[i]}%` }}></div>
                      <div className="v4m-slider-knob" style={{ left: `${sliders[i]}%` }}></div>
                    </div>
                    <input
                      type="range" className="range-overlay"
                      min={0} max={100} value={sliders[i]}
                      onChange={e => {
                        const v = parseInt(e.target.value, 10);
                        setSliders(prev => {
                          if (!prev) return prev;
                          const next = [...prev];
                          next[i] = v;
                          return next;
                        });
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <button className={`v4m-cta${busy ? ' busy' : ''}${qpuCoolingDown ? ' cooldown' : ''}`} onClick={retune} disabled={retuneDisabled}>
              <span>{retuneButtonText}</span>
              <span className="v4m-cta-arrow">→</span>
            </button>
            {retuneHelper && <div className="v4m-cta-sub">{retuneHelper}</div>}

            </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
