import { useEffect, useMemo, useState } from 'react';
import { getValuationHistory } from '../../api';
import type { LeaderboardEntry, RoutingStats, ValuationHistoryPoint } from '../../api';
import RoutingStatsPanel from './RoutingStatsPanel';
import Countdown from './Countdown';
import { useTween } from '../../utils/anim';

export default function StateB({
  leaderboard,
  rankIndex,
  routingStats,
  phaseSeconds = 15,
}: {
  leaderboard: LeaderboardEntry[];
  rankIndex: number;
  routingStats: RoutingStats;
  phaseSeconds?: number;
}) {
  // Fall back to the top agent if the spotlight index is ever out of range
  // (e.g. a NaN from a transiently empty board); BoothTV guarantees ≥1 entry.
  const agent = leaderboard[rankIndex % leaderboard.length] ?? leaderboard[0];
  const [history, setHistory] = useState<ValuationHistoryPoint[]>([]);
  const tweenTotal = useTween(agent.total, { durationMs: 600 });
  const rankPadded = String(agent.rank).padStart(2, '0');
  const displayPct = Math.round(agent.plPct * 100) / 100;
  const lineColor = displayPct > 0 ? '#0A832E' : displayPct < 0 ? '#ff6467' : '#71717b';
  const changePrefix = displayPct > 0 ? '+' : displayPct < 0 ? '−' : '';
  const { sparkPath, sparkFill } = useMemo(
    () => buildSparkline(history, agent.total),
    [history, agent.total],
  );

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const points = await getValuationHistory(agent.agentId, 60);
        if (!cancelled) setHistory(points);
      } catch {
        if (!cancelled) setHistory([]);
      }
    };
    refresh();
    const interval = window.setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [agent.agentId]);

  return (
    <div className="bigscreen dir-quipsite v4 state-c">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum.Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Spotlight · Rank {rankPadded}</span><span className="bar"></span></div>
      </div>

      <div className="qs-body-v4">
        <div className="qs-hero-left">
          <div className="left">
            <h1>Rank {rankPadded} · <span className="it">{agent.name}.</span></h1>
            <div className="spot-handle">02h 14m on the board</div>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>Spotlight</div>
            <div className="countdown" style={{ fontFamily: 'Georgia,serif', fontStyle: 'italic', fontSize: '3.4cqh', color: '#18181b', fontVariantNumeric: 'tabular-nums' }}><Countdown seconds={phaseSeconds} /></div>
          </div>
        </div>

        <div className="qs-table-area">
          <div className="spot-stage">
            <div className="spot-stats">
              <div className="ss-cell">
                <div className="ss-lbl">Total P&amp;L</div>
                <div className="ss-val ss-pl">${Math.round(tweenTotal).toLocaleString()}</div>
              </div>
              <div className="ss-cell">
                <div className="ss-lbl">Change</div>
                <div className="ss-val ss-change" style={{ color: lineColor }}>{changePrefix}{Math.abs(displayPct).toFixed(2)}%</div>
              </div>
              <div className="ss-cell">
                <div className="ss-lbl">Current rank</div>
                <div className="ss-val ss-rank">{rankPadded}</div>
              </div>
              <div className="ss-cell">
                <div className="ss-lbl">Jobs solved</div>
                <div className="ss-val ss-jobs">{agent.jobsSolved}</div>
              </div>
            </div>

            <div className="spot-spark">
              <svg viewBox="0 0 600 90" preserveAspectRatio="none" aria-hidden="true">
                <defs>
                  <linearGradient id="spotSparkFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
                    <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
                  </linearGradient>
                </defs>
                <polyline fill="url(#spotSparkFill)" stroke="none" points={sparkFill} />
                <polyline fill="none" stroke={lineColor} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" points={sparkPath} />
              </svg>
            </div>

            <div className="spot-lastsolve">
              <div className={`v4-pr ${agent.primaryProvider === 'QPU' ? 'q' : 'c'}`}>
                <span className="type">{agent.primaryProvider}</span>
                <span className="nm">Solved by {agent.primaryProvider === 'QPU' ? 'D-Wave Advantage' : 'Helios-12'}</span>
                <span className="pct" style={{ fontFamily: "'JetBrains Mono',monospace", color: '#71717b' }}>4s ago</span>
              </div>
            </div>
          </div>
        </div>

        <aside className="qs-rail v4-rail">
          <div className="v4-mega">
            <RoutingStatsPanel stats={routingStats} />

            <div className="v4-section">
              <div className="v3-panel-head">
                <span className="v3-panel-eyebrow">Current standings</span>
                <span className="v3-panel-hero">Top <span className="accent">ten.</span></span>
              </div>
              <div className="v3-panel-body">
                <div className="mini-lb">
                  {leaderboard.map(row => {
                    const isSpotlit = row.rank === agent.rank;
                    const top = row.rank <= 3 ? ` top${row.rank}` : '';
                    return (
                      <div className={`qs-row${top}${isSpotlit ? ' spotlit' : ''}`} key={row.agentId}>
                        <span className="rank">{String(row.rank).padStart(2, '0')}</span>
                        <span className="name">{row.name}</span>
                        <span className="pnl tv-tick" key={`p${Math.round(row.total)}`}>${Math.round(row.total).toLocaleString()}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function buildSparkline(history: ValuationHistoryPoint[], currentTotal: number) {
  const values = history
    .map(point => point.total)
    .filter(value => Number.isFinite(value));
  const last = values[values.length - 1];
  if (last === undefined || Math.abs(last - currentTotal) >= 0.005) {
    values.push(currentTotal);
  }
  if (values.length === 1) {
    values.push(values[0]);
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const width = 600;
  const height = 90;
  const padY = 8;
  const usableHeight = height - padY * 2;
  const path = values.map((value, index) => {
    const x = values.length === 1 ? 0 : (index / (values.length - 1)) * width;
    const y = span <= 0 ? height / 2 : padY + ((max - value) / span) * usableHeight;
    return `${roundCoord(x)},${roundCoord(y)}`;
  }).join(' ');

  return {
    sparkPath: path,
    sparkFill: `${path} ${width},${height} 0,${height}`,
  };
}

function roundCoord(value: number): number {
  return Math.round(value * 10) / 10;
}
