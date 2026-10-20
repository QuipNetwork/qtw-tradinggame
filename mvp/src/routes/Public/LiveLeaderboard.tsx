import { IS_MOCK, type LeaderboardEntry } from '../../api';
import { useFlipList } from '../../utils/flip';
import TickValue from '../../components/TickValue';
import { fmtUsd } from '../../utils/format';

// Deterministic two-tone avatar from the agent id — cheap stand-in for the
// generative glyph at row scale, drawn from the brand palette.
const AV = ['#FF6C78', '#4CE0FF', '#FFDE53', '#67E347', '#FF92D5', '#A5C3D4'];
function avatar(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return `linear-gradient(135deg, ${AV[h % AV.length]}, ${AV[(h >> 3) % AV.length]})`;
}

function lastAgentId(): string | null {
  try {
    return localStorage.getItem('quip:lastAgentId');
  } catch {
    return null;
  }
}

// Live leaderboard; the landing page polls and passes the rows (null until the first
// poll answers). Rows FLIP-glide when ranks change; P&L flashes on each tick. The
// player's own agent (cookie) is highlighted "YOU".
export default function LiveLeaderboard({
  rows,
  failed = false,
  limit = 8,
}: {
  rows: LeaderboardEntry[] | null;
  failed?: boolean;
  limit?: number;
}) {
  const mine = lastAgentId();
  const shown = (rows ?? []).slice(0, limit);
  const orderKey = shown.map(r => r.agentId).join('>');
  const listRef = useFlipList<HTMLDivElement>(orderKey);

  return (
    <section id="leaderboard" className="qpub-section qpub-board" data-reveal>
      <div className="qpub-board-head">
        <h2>Leaderboard</h2>
        {IS_MOCK && <span className="qpub-board-note">Demo data</span>}
        {/* A failed poll keeps the last rows; say they may be stale. */}
        {failed && shown.length > 0 && <span className="qpub-board-note">Reconnecting…</span>}
      </div>

      <div className="qpub-board-cols" aria-hidden>
        <span>Rank</span><span>Agent</span><span>Solver</span><span>Total</span><span className="r">P&amp;L</span>
      </div>

      <div className="qpub-board-rows" ref={listRef}>
        {shown.map(row => {
          const pos = row.plPct > 0;
          const sign = row.plPct > 0 ? '+' : row.plPct < 0 ? '−' : '';
          return (
            <div
              className={`qpub-row${row.agentId === mine ? ' is-you' : ''}${row.rank <= 3 ? ' is-top' : ''}`}
              data-flip-key={row.agentId}
              key={row.agentId}
            >
              <span className="qpub-rk">{String(row.rank).padStart(2, '0')}</span>
              <span className="qpub-ag">
                <span className="qpub-av" style={{ background: avatar(row.agentId) }} />
                <span className="qpub-ag-id">
                  <span className="qpub-ag-name">{row.name}</span>
                  {row.handle && <span className="qpub-ag-handle">{row.handle}</span>}
                </span>
              </span>
              <span className={`qpub-solver ${row.primaryProvider === 'QPU' ? 'q' : 'c'}`}>{row.primaryProvider}</span>
              <span className="qpub-total">{fmtUsd(row.total)}</span>
              <TickValue
                className={`qpub-pnl ${pos ? 'up' : row.plPct < 0 ? 'dn' : ''}`}
                value={Math.round(row.plPct * 100)}
                text={`${sign}${Math.abs(row.plPct).toFixed(2)}%`}
              />
            </div>
          );
        })}
        {shown.length === 0 && <div className="qpub-board-empty">{emptyText(rows, failed)}</div>}
      </div>
    </section>
  );
}

// What an empty board means: still loading, unreachable, or no agents yet.
function emptyText(rows: LeaderboardEntry[] | null, failed: boolean): string {
  if (failed) return 'Leaderboard unavailable, retrying…';
  if (rows === null) return 'Loading the board…';
  return 'No agents yet. Be the first at the booth.';
}
