import type { LeaderboardEntry } from '../../api';

const CLASSICAL_BREAKDOWN = [
  { name: 'Helios-12', pct: 3 },
  { name: 'Falcon-7',  pct: 2 },
  { name: 'Cumulus-3', pct: 2 },
  { name: 'Atlas-9',   pct: 1 },
  { name: 'Nimbus-5',  pct: 1 },
  { name: 'Stratos-2', pct: 1 },
  { name: 'Cirrus-8',  pct: 1 },
  { name: 'Boreas-4',  pct: 1 },
];

const MEDALS = ['🥇', '🥈', '🥉'];

export default function StateA({ leaderboard }: { leaderboard: LeaderboardEntry[] }) {
  return (
    <div className="bigscreen dir-quipsite v4">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Live · Top Ten</span><span className="bar"></span></div>
      </div>

      <div className="qs-body-v4">
        <div className="qs-hero-left">
          <div className="left">
            <h1>Top ten <span className="it">quantum trading agents.</span></h1>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>Refreshing in</div>
            <div className="countdown" style={{ fontFamily: 'Georgia,serif', fontStyle: 'italic', fontSize: '3.4cqh', color: '#18181b', fontVariantNumeric: 'tabular-nums' }}>02.5s</div>
          </div>
        </div>

        <div className="qs-table-area">
          <div className="qs-table">
            <div className="th"><span className="rk">Rank</span><span className="nm">Agent</span><span className="pnl">Total P&amp;L</span><span className="change">Δ%</span></div>
            {leaderboard.map((row) => {
              const rankClass = row.rank <= 3 ? ` top${row.rank}` : '';
              const changeClass = row.plPct < 0 ? 'change down' : 'change';
              return (
                <div className={`qs-row${rankClass}`} key={row.agentId}>
                  <span className="rank">
                    {String(row.rank).padStart(2, '0')}
                    {row.rank <= 3 && <span className="medal">{MEDALS[row.rank - 1]}</span>}
                  </span>
                  <span className="name">{row.name}</span>
                  <span className="pnl">${row.total.toLocaleString()}</span>
                  <span className={changeClass}>{row.plPct >= 0 ? '+' : '−'}{Math.abs(row.plPct).toFixed(2)}%</span>
                </div>
              );
            })}
          </div>
        </div>

        <aside className="qs-rail v4-rail">
          <div className="v4-mega">
            <div className="v4-section">
              <div className="v3-panel-head">
                <span className="v3-panel-eyebrow">Routing today</span>
                <span className="v3-panel-hero">Quantum <span className="accent">vs</span> classical.</span>
              </div>
              <div className="v3-panel-body">
                <div className="v3-qc">
                  <div className="num-row">
                    <span className="num-q">88<span className="pct">%</span></span>
                    <span className="num-c">12<span className="pct">%</span></span>
                  </div>
                  <div className="names">
                    <span className="n-q">Quantum (QPU)</span>
                    <span className="n-c">Classical (CPU)</span>
                  </div>
                  <div className="ms-bar"><span className="q"></span><span className="c"></span></div>
                </div>
              </div>
            </div>

            <div className="v4-section">
              <div className="v3-panel-head">
                <span className="v3-panel-eyebrow">Top providers</span>
                <span className="v3-panel-hero">Top Providers</span>
              </div>
              <div className="v3-panel-body">
                <div className="v4-plist">
                  <div className="v4-stack">
                    <span className="seg q"  style={{ width: '88%' }}></span>
                    {CLASSICAL_BREAKDOWN.map((p, i) => (
                      <span key={p.name} className={`seg c${i + 1}`} style={{ width: `${p.pct}%` }}></span>
                    ))}
                  </div>
                  <div className="v4-pr q"><span className="type">QPU</span><span className="nm">D-Wave Advantage</span><span className="pct">88%</span></div>
                  {CLASSICAL_BREAKDOWN.map(p => (
                    <div className="v4-pr c" key={p.name}>
                      <span className="type">CPU</span><span className="nm">{p.name}</span><span className="pct">{p.pct}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
