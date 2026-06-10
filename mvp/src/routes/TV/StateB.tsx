import type { LeaderboardEntry } from '../../api';

export default function StateB({ leaderboard, rankIndex }: { leaderboard: LeaderboardEntry[]; rankIndex: number }) {
  const agent = leaderboard[rankIndex % leaderboard.length];
  const rankPadded = String(agent.rank).padStart(2, '0');
  const positive = agent.plPct >= 0;
  const lineColor = positive ? '#0A832E' : '#ff6467';
  const sparkPath = positive
    ? '0,72 40,70 80,66 120,68 160,60 200,58 240,52 280,55 320,46 360,40 400,42 440,33 480,28 520,22 560,18 600,12'
    : '0,18 40,22 80,28 120,26 160,34 200,38 240,44 280,40 320,48 360,54 400,52 440,60 480,66 520,72 560,78 600,82';
  const sparkFill = positive
    ? `${sparkPath} 600,90 0,90`
    : `${sparkPath} 600,90 0,90`;

  return (
    <div className="bigscreen dir-quipsite v4 state-c">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Spotlight · Rank {rankPadded} · Day 1</span><span className="bar"></span></div>
      </div>

      <div className="qs-body-v4">
        <div className="qs-hero-left">
          <div className="left">
            <h1>Rank {rankPadded} · <span className="it">{agent.name}.</span></h1>
            <div className="spot-handle">02h 14m on the board</div>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>Spotlight</div>
            <div className="countdown" style={{ fontFamily: 'Georgia,serif', fontStyle: 'italic', fontSize: '3.4cqh', color: '#18181b', fontVariantNumeric: 'tabular-nums' }}>12s</div>
          </div>
        </div>

        <div className="qs-table-area">
          <div className="spot-stage">
            <div className="spot-stats">
              <div className="ss-cell">
                <div className="ss-lbl">Total P&amp;L</div>
                <div className="ss-val ss-pl">${agent.total.toLocaleString()}</div>
              </div>
              <div className="ss-cell">
                <div className="ss-lbl">Change</div>
                <div className="ss-val ss-change" style={{ color: lineColor }}>{agent.plPct >= 0 ? '+' : '−'}{Math.abs(agent.plPct).toFixed(2)}%</div>
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
                        <span className="pnl">${row.total.toLocaleString()}</span>
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
