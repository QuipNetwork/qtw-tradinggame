import type { LeaderboardEntry, RoutingStats } from '../../api';
import RoutingStatsPanel from './RoutingStatsPanel';
import Countdown from './Countdown';
import { fmtUsd } from '../../utils/format';

const MEDALS = ['🥇', '🥈', '🥉'];

export default function StateA({
  leaderboard,
  routingStats,
  phaseSeconds = 12,
}: {
  leaderboard: LeaderboardEntry[];
  routingStats: RoutingStats;
  phaseSeconds?: number;
}) {
  return (
    <div className="bigscreen dir-quipsite v4">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum.Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Live · Top Ten</span><span className="bar"></span></div>
      </div>

      <div className="qs-body-v4">
        <div className="qs-hero-left">
          <div className="left">
            <h1>Top ten <span className="it">quantum</span> trading agents.</h1>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>Next view in</div>
            <div className="countdown" style={{ fontFamily: 'Georgia,serif', fontStyle: 'italic', fontSize: '3.4cqh', color: '#18181b', fontVariantNumeric: 'tabular-nums' }}><Countdown seconds={phaseSeconds} /></div>
          </div>
        </div>

        <div className={`qs-table-area${leaderboard.length < 10 ? ' top-align' : ''}`}>
          <div className="qs-table">
            <div className="th"><span className="rk">Rank</span><span className="nm">Agent</span><span className="pnl">Total P&amp;L</span><span className="change">▲%</span></div>
            {leaderboard.map((row) => {
              const rankClass = row.rank <= 3 ? ` top${row.rank}` : '';
              const changeClass = row.plPct < 0 ? 'change down' : 'change';
              return (
                <div className={`qs-row${rankClass}`} key={row.agentId}>
                  <span className="rank">
                    <span className="rank-num">{String(row.rank).padStart(2, '0')}</span>
                    {row.rank <= 3 && <span className="medal">{MEDALS[row.rank - 1]}</span>}
                  </span>
                  <span className="name">{row.name}</span>
                  <span className="pnl tv-tick" key={`p${Math.round(row.total)}`}>{fmtUsd(row.total)}</span>
                  <span className={changeClass}>{row.plPct >= 0 ? '+' : '−'}{Math.abs(row.plPct).toFixed(2)}%</span>
                </div>
              );
            })}
          </div>
        </div>

        <aside className="qs-rail v4-rail">
          <div className="v4-mega">
            <RoutingStatsPanel stats={routingStats} showRecent />
          </div>
        </aside>
      </div>
    </div>
  );
}
