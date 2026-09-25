import { useMemo } from 'react';
import type { LeaderboardEntry, RoutingStats } from '../../api';
import RoutingStatsPanel from './RoutingStatsPanel';
import Countdown from './Countdown';
import { useTween } from '../../utils/anim';
import { fmtUsd } from '../../utils/format';
import TickValue from '../../components/TickValue';

export default function StateB({
  leaderboard,
  rankIndex,
  routingStats,
  totals,
  phaseSeconds = 15,
}: {
  leaderboard: LeaderboardEntry[];
  rankIndex: number;
  routingStats: RoutingStats;
  totals: number[];
  phaseSeconds?: number;
}) {
  // Fall back to the top agent if the spotlight index is ever out of range
  // (e.g. a NaN from a transiently empty board); BoothTV guarantees ≥1 entry.
  const agent = leaderboard[rankIndex % leaderboard.length] ?? leaderboard[0];
  const tweenTotal = useTween(agent.total, { durationMs: 600 });
  const rankPadded = String(agent.rank).padStart(2, '0');
  const displayPct = Math.round(agent.plPct * 100) / 100;
  const lineColor = displayPct > 0 ? '#0A832E' : displayPct < 0 ? '#ff6467' : '#71717b';
  const changePrefix = displayPct > 0 ? '+' : displayPct < 0 ? '−' : '';
  // Live P&L curve from the rolling leaderboard-total buffer BoothTV maintains
  // (the per-agent history endpoint is token-gated; the TV can't read it). Falls
  // back to a flat line at the current total until the buffer has ≥2 points.
  const { sparkPath, sparkFill } = useMemo(
    () => buildSparkline(totals.length ? totals : [agent.total]),
    [totals, agent.total],
  );

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
            <div className="spot-handle">{agent.handle ?? `Rank ${rankPadded} on the leaderboard`}</div>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>Up next</div>
            <div className="countdown" style={{ fontFamily: 'Georgia,serif', fontStyle: 'italic', fontSize: '3.4cqh', color: '#18181b', fontVariantNumeric: 'tabular-nums' }}><Countdown seconds={phaseSeconds} /></div>
          </div>
        </div>

        <div className="qs-table-area">
          <div className="spot-stage">
            <div className="spot-stats">
              <div className="ss-cell">
                <div className="ss-lbl">Total P&amp;L</div>
                <div className="ss-val ss-pl">{fmtUsd(tweenTotal)}</div>
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
                <span className="nm">Solved by {agent.primaryProvider === 'QPU' ? 'D-Wave Advantage' : agent.primaryProvider === 'NETWORK' ? 'Quip testnet' : 'Simulated Annealing'}</span>
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
                        <TickValue className="pnl" value={Math.round(row.total)} text={fmtUsd(row.total)} />
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

function buildSparkline(rawValues: number[]) {
  const values = rawValues.filter(value => Number.isFinite(value));
  if (values.length === 0) return { sparkPath: '', sparkFill: '' };
  if (values.length === 1) {
    values.push(values[0]);   // a single point → a flat line
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
