import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import type {
  AgentConfig,
  RoutingResult,
  LeaderboardEntry,
  SliderValues,
  AssetTicker,
  AssetInfo,
  QpuBudgetStatus,
} from '../../api';
import { getAgent, getLeaderboard, requestOptimization, updateAgent, ASSETS, CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc, assetColor, ASSET_BY_TICKER } from '../../api';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';
import { solverRaceComparison, solverRaceRows } from '../../utils/solverRace';
import { glyphParams, labelFor, slidersToArray, holdCountDefault, holdCountMax, clampHoldCount } from '../../utils/strategy';
import { useAgentLive } from '../../hooks/useAgentLive';
import RebalanceSlider from '../../components/RebalanceSlider';
import { useTweens } from '../../utils/anim';
import StatusScreen from '../../components/StatusScreen';
import TickValue from '../../components/TickValue';
import { WHOLE_USD, fmtUsd } from '../../utils/format';

const SLIDER_DEFS: Array<{ key: keyof SliderValues; label: string }> = [
  { key: 'rebalanceFrequency', label: 'Rebalance frequency' },
  { key: 'riskPreference',     label: 'Risk preference' },
  { key: 'maxPositionSize',    label: 'Max position size' },
];

// A basket needs at least this many assets (mirrors the kiosk sign-up rule).
const MIN_ASSETS = 3;
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

// Sparkline coordinates over the rolling total buffer, in the 80×36 viewBox.
// Returns points (for the polyline) so the caller can also place an eased head
// dot at the latest one. A 2px side margin keeps the dot clear of the edges.
function sparkCoords(values: number[]): Array<{ x: number; y: number }> {
  const series = values.length >= 2 ? values : [10000, 10000];
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = Math.max(1, max - min);
  return series.map((value, i) => ({
    x: (i / Math.max(1, series.length - 1)) * 76 + 2,
    y: 32 - ((value - min) / range) * 25,
  }));
}

export default function PhoneProfile() {
  const { agentId } = useParams();
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [sliders, setSliders] = useState<number[] | null>(null);
  const [holdCount, setHoldCount] = useState<number | null>(null);
  const [result, setResult] = useState<RoutingResult | null>(null);
  const { update: live } = useAgentLive(agentId);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<'profile' | 'basket'>('profile');
  const [basket, setBasket] = useState<Set<AssetTicker>>(new Set());
  const [savingBasket, setSavingBasket] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalHistory, setTotalHistory] = useState<number[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [qpuCooldownUntilMs, setQpuCooldownUntilMs] = useState<number | null>(null);
  const [rankInfo, setRankInfo] = useState<RankInfo | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'notfound' | 'error'>('loading');
  const [retryNonce, setRetryNonce] = useState(0);
  const glyphRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!agentId) return;
    let cancelled = false;
    setLoadState('loading');
    (async () => {
      try {
        const a = await getAgent(agentId);
        if (cancelled) return;
        if (!a) { setLoadState('notfound'); return; }
        setAgent(a);
        setSliders(slidersToArray(a.sliders));
        setHoldCount(a.sliders.holdCount ?? null);
        setBasket(new Set(a.assets ?? []));
        const targetMs = qpuCooldownTargetMs(a.qpuBudget);
        if (targetMs && targetMs > Date.now()) setQpuCooldownUntilMs(targetMs);

        const cachedRaw = sessionStorage.getItem('quip:lastResult:' + agentId);
        if (cachedRaw) {
          try {
            const cached = JSON.parse(cachedRaw) as RoutingResult;
            setResult(cached);
            const cachedTargetMs = qpuCooldownTargetMs(cached.qpuBudget);
            if (cachedTargetMs && cachedTargetMs > Date.now()) setQpuCooldownUntilMs(cachedTargetMs);
          } catch { /* ignore a corrupt cache entry */ }
        }
        setLoadState('ready');
      } catch {
        if (!cancelled) setLoadState('error');
      }
    })();
    return () => { cancelled = true; };
  }, [agentId, retryNonce]);

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

  // React to each live tick: extend the sparkline buffer and honor any QPU
  // cooldown the backend reports on the stream. The subscription itself is owned
  // by useAgentLive.
  useEffect(() => {
    if (!live) return;
    setTotalHistory(prev => [...prev, live.total].slice(-32));
    const targetMs = qpuCooldownTargetMs(live.qpuBudget);
    if (targetMs && targetMs > Date.now()) setQpuCooldownUntilMs(targetMs);
  }, [live]);

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

  // Live values, tweened so the numbers count smoothly toward each tick. These
  // are hooks, so they must run before the early returns below.
  // Neutral until the first live tick — never show a fabricated gain.
  const liveTotal = live?.total ?? 10000;
  const livePlUSD = live?.plUSD ?? 0;
  const livePlPct = live?.plPct ?? 0;
  const [tweenTotal, tweenPlUSD, tweenPlPct] = useTweens([liveTotal, livePlUSD, livePlPct]);

  const phoneFrame = (body: ReactNode) => (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#0a0a10', padding: 16 }}>
      <div className="mockup-frame phone dark">
        <div className="screen">
          <div className="qs-v4-mock phone-v4">{body}</div>
        </div>
      </div>
    </div>
  );

  if (!agentId) return phoneFrame(<StatusScreen tone="dark" title="Missing agent" message="This link has no agent id." action={{ label: 'Open kiosk', href: '/kiosk' }} />);
  if (loadState === 'notfound') return phoneFrame(<StatusScreen tone="dark" title="Profile not found" message="The link may be stale or the agent was reset." action={{ label: 'Open kiosk', href: '/kiosk' }} />);
  if (loadState === 'error') return phoneFrame(<StatusScreen tone="dark" title="Can't reach Quip Network" message="We couldn't load your profile. Check your connection and try again." action={{ label: 'Retry', onClick: () => setRetryNonce(n => n + 1) }} />);
  if (!agent || !sliders) return phoneFrame(<StatusScreen tone="dark" busy title="Loading your profile…" />);

  async function retune() {
    if (busy || !agentId || !sliders) return;
    setBusy(true);
    setError(null);
    const next: SliderValues = SLIDER_DEFS.reduce<SliderValues>((acc, def, i) => {
      acc[def.key] = sliders[i];
      return acc;
    }, {} as SliderValues);
    const assets = ASSETS.filter(a => basket.has(a.ticker)).map(a => a.ticker);
    // Method 3 cardinality K, clamped to the (possibly edited) basket. Default =
    // round(N/3) and capped at N−1 so it stays a real selection (K = N is degenerate).
    next.holdCount = clampHoldCount(holdCount ?? holdCountDefault(assets.length), assets.length);
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

  const pnl = roundedPnL(livePlUSD, livePlPct);
  const lineColor = pnl.tone === 'down' ? '#ff6467' : pnl.tone === 'up' ? '#0A832E' : '#71717b';
  const totalText = WHOLE_USD.format(Math.max(0, Math.round(tweenTotal)));
  const usdText = WHOLE_USD.format(Math.abs(Math.round(tweenPlUSD)));
  const pctText = Math.abs(tweenPlPct).toFixed(2);
  const sparkXY = sparkCoords(totalHistory);
  const sparkStr = sparkXY.map(p => `${p.x},${p.y}`).join(' ');
  const sparkHead = sparkXY[sparkXY.length - 1];

  // Live portfolio for the holdings strip — prefer the streamed holdings (they
  // move with price), fall back to the last solve, drop unknown tickers.
  const holdings = (live?.holdings?.length
    ? live.holdings.map(h => ({ ticker: h.ticker, pct: h.pct, usd: h.usd }))
    : result?.portfolio ?? []
  ).filter(e => ASSET_BY_TICKER[e.ticker]);

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
            <main className="v4m-phone-view">

            <div className="v4m-phone-head">
              <div>
                <h1 className="v4m-phone-name">{agent.name}</h1>
              </div>
              <canvas ref={glyphRef} width={56} height={56} aria-hidden="true"></canvas>
              <div className="v4m-phone-rank" style={{ gridColumn: '1 / 3', marginTop: 4, justifySelf: 'start' }}>
                <span>You're</span>
                <span className="v4m-rank-num">{rankText}</span>
                <span>{rankTotalText}</span>
              </div>
            </div>

            <div className="v4m-pl">
              <div>
                <div className="v4m-section-eyebrow">Total{live?.stale ? ' · Last close' : ''}</div>
                <div className="v4m-pl-num">${totalText}</div>
                <div className={`v4m-pl-change ${pnl.tone}`}>
                  {pnl.sign}${usdText} · {pnl.sign}{pctText}%
                </div>
                {/* One settled announcement per tick (the visible numbers tween silently). */}
                <span className="sr-only" aria-live="polite">
                  Total ${WHOLE_USD.format(Math.round(liveTotal))}, {pnl.tone === 'up' ? 'up' : pnl.tone === 'down' ? 'down' : 'flat'} {pnl.pct} percent
                </span>
              </div>
              <svg className="v4m-spark" viewBox="0 0 80 36" preserveAspectRatio="none" aria-hidden="true" style={{ color: lineColor }}>
                <polyline
                  points={sparkStr}
                  fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                />
                {sparkHead && (
                  <circle className="v4m-spark-dot" cx={sparkHead.x} cy={sparkHead.y} r="2.6" fill="currentColor" />
                )}
              </svg>
            </div>

            {holdings.length > 0 && (
            <div className="v4m-holds">
              <div className="v4m-section-eyebrow">Holdings · {holdings.length}</div>
              <div className="v4m-alloc-stack" style={{ marginTop: 8 }}>
                {holdings.map(h => (
                  <span key={h.ticker} className="v4m-alloc-seg" style={{ width: `${h.pct}%`, background: assetColor(h.ticker) }}></span>
                ))}
              </div>
              <div className="v4m-holds-list">
                {holdings.slice(0, 6).map(h => (
                  <div className="v4m-holds-row" key={h.ticker}>
                    <img className="v4m-holds-icon" src={assetIconSrc(h.ticker)} alt="" />
                    <span className="v4m-holds-ticker">{h.ticker}</span>
                    <span className="v4m-holds-pct">{Math.round(h.pct)}%</span>
                    <TickValue className="v4m-holds-usd" value={Math.round(h.usd)} text={fmtUsd(h.usd)} />
                  </div>
                ))}
                {holdings.length > 6 && <div className="v4m-holds-more">+{holdings.length - 6} more held</div>}
              </div>
            </div>
            )}

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
                      {row.detail && <span className="v4m-race-detail">{row.detail}</span>}
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
                  {labelFor(0, sliders[0]) === 'Off'
                    ? 'Rebalancing is off'
                    : rebalanceIntervalHours == null
                      ? 'Starts after first solve'
                      : rebalanceIntervalHours < 1
                        ? `Every ${Math.round(rebalanceIntervalHours * 60)}m cadence`
                        : `Every ${rebalanceIntervalHours}h cadence`}
                </div>
              </div>
              <div className="v4m-rebalance-time">{labelFor(0, sliders[0]) === 'Off' ? '—' : rebalanceCountdown}</div>
            </div>

            <button type="button" className="v4m-basket-open" onClick={() => setView('basket')}>
              <span className="v4m-section-eyebrow">Your basket · {basket.size} asset{basket.size === 1 ? '' : 's'}</span>
              <span className="v4m-basket-open-cta">Edit →</span>
            </button>

            <div>
              <div className="v4m-section-eyebrow" style={{ marginBottom: 8 }}>Strategy · Drag to Retune</div>
              {SLIDER_DEFS.map((def, i) =>
                def.key === 'rebalanceFrequency' ? null : (
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
                        aria-label={def.label}
                        aria-valuetext={labelFor(i, sliders[i])}
                        onChange={e => {
                          const v = parseInt(e.target.value, 10);
                          setSliders(prev => {
                            if (!prev) return prev;
                            const nx = [...prev];
                            nx[i] = v;
                            return nx;
                          });
                        }}
                      />
                    </div>
                  </div>
                )
              )}
              {/* Number to hold (K) — the third slider; a count tied to the basket. */}
              {(() => {
                const n = basket.size;
                const ready = n >= 3;
                const maxK = holdCountMax(n);
                const k = ready ? clampHoldCount(holdCount ?? holdCountDefault(n), n) : 3;
                const pct = ready ? (maxK > 3 ? ((k - 3) / (maxK - 3)) * 100 : 100) : 0;
                return (
                  <div className={`v4m-slider${ready ? '' : ' disabled'}`} key="holdCount">
                    <div className="v4m-slider-top">
                      <span className="v4m-slider-label">Number to hold</span>
                      <span className="v4m-slider-val">
                        {ready ? `${k} of ${n}` : 'edit basket'}
                      </span>
                    </div>
                    <div className="v4m-slider-shell">
                      <div className="v4m-slider-track">
                        <div className="v4m-slider-fill" style={{ width: `${pct}%` }}></div>
                        <div className="v4m-slider-knob" style={{ left: `${pct}%` }}></div>
                      </div>
                      <input
                        type="range" className="range-overlay"
                        min={3} max={maxK} step={1} value={k}
                        aria-label="Number to hold"
                        aria-valuetext={ready ? `${k} of ${n}` : 'Edit basket first'}
                        disabled={!ready}
                        onChange={e => setHoldCount(parseInt(e.target.value, 10))}
                      />
                    </div>
                  </div>
                );
              })()}
              {/* Rebalance cadence — segmented heat-bar slider (RebalanceSlider). */}
              <RebalanceSlider
                value={sliders[0]}
                onChange={v =>
                  setSliders(prev => {
                    if (!prev) return prev;
                    const nx = [...prev];
                    nx[0] = v;
                    return nx;
                  })
                }
              />
            </div>

            <button className={`v4m-cta${busy ? ' busy' : ''}${qpuCoolingDown ? ' cooldown' : ''}`} onClick={retune} disabled={retuneDisabled}>
              <span>{retuneButtonText}</span>
              <span className="v4m-cta-arrow">→</span>
            </button>
            {retuneHelper && <div className="v4m-cta-sub">{retuneHelper}</div>}

            </main>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
