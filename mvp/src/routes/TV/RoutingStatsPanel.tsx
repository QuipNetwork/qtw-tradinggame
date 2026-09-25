import type { RoutingStats } from '../../api';

type Props = {
  stats: RoutingStats;
  showRecent?: boolean;
};

function fmtSecs(s: number | null): string {
  return s == null ? '—' : `${s.toFixed(2)}s`;
}

// How many recent routings to list. Two-line, TV-legible rows — readability
// over density, so fewer fit.
const DETAIL_ROWS = 5;

export default function RoutingStatsPanel({ stats, showRecent = false }: Props) {
  const qpuPct = Math.round(stats.qpuPct);
  const cpuPct = Math.round(stats.cpuPct);
  const qpuWidth = stats.total > 0 ? stats.qpuPct : 0;
  const cpuWidth = stats.total > 0 ? stats.cpuPct : 0;
  const recent = stats.recent ?? [];  // tolerate an older backend without the field

  // The leading solver gets the dominant number; a tie (incl. the 0–0 default)
  // keeps both equal. We don't assume QPU wins — whoever leads grows.
  const qpuState = stats.qpuPct === stats.cpuPct ? 'even' : stats.qpuPct > stats.cpuPct ? 'lead' : 'trail';
  const cpuState = stats.qpuPct === stats.cpuPct ? 'even' : stats.cpuPct > stats.qpuPct ? 'lead' : 'trail';

  return (
    <>
      <div className="v4-section">
        <div className="v3-panel-head">
          <span className="v3-panel-eyebrow">All solves · win rate</span>
          <span className="v3-panel-hero">{stats.networkWins ? 'Network, quantum & classical.' : <>Quantum <span className="accent">vs</span> classical.</>}</span>
        </div>
        <div className="v3-panel-body">
          <div className="v3-qc">
            <div className="num-row">
              <span className={`num-q ${qpuState}`}>{qpuPct}<span className="pct">%</span></span>
              <span className={`num-c ${cpuState}`}>{cpuPct}<span className="pct">%</span></span>
            </div>
            <div className="names">
              <span className="n-q">Quantum (QPU)</span>
              <span className="n-c">Classical (CPU)</span>
            </div>
            <div className="ms-bar">
              <span className="q" style={{ width: `${qpuWidth}%` }}></span>
              <span className="c" style={{ width: `${cpuWidth}%` }}></span>
            </div>
            {!!stats.networkWins && <div>Quip network: {stats.networkWins} wins ({Math.round(stats.networkPct ?? 0)}%)</div>}
          </div>
        </div>
      </div>

      {showRecent && (
        <div className="v4-section">
          <div className="v3-panel-head">
            <span className="v3-panel-eyebrow">Recent routings</span>
            <span className="v3-panel-hero">Most recently <span className="accent">routed.</span></span>
          </div>
          <div className="v3-panel-body">
            {recent.length > 0 ? (
              <div className="v4-feed">
                <div className="v4-feed-rows">
                  {recent.slice(0, DETAIL_ROWS).map((r, i) => {
                    const altType = r.providerType === 'NETWORK' ? 'another solver' : r.providerType === 'CPU' ? 'QPU' : 'CPU';
                    const faster =
                      r.vsTime != null && r.vsTime > r.solveTime
                        ? Math.round(((r.vsTime - r.solveTime) / r.vsTime) * 100)
                        : null;
                    // Backend-classified outcome so a quality+speed TIE never reads as a misleading
                    // "X% faster": tie → both found the best portfolio at ~the same time; speed →
                    // winner genuinely faster; quality → winner's portfolio is better (may be slower).
                    // No runner-up time → it never returned a usable result (infeasible / DNF).
                    const line2 =
                      r.outcome === 'tie' ? (
                        <>Tied with {altType} <span className="alt">({fmtSecs(r.vsTime)})</span></>
                      ) : r.outcome === 'speed' ? (
                        <>{faster ?? 0}% faster than {altType} <span className="alt">({fmtSecs(r.vsTime)})</span></>
                      ) : r.vsTime != null ? (
                        <>Best portfolio <span className="alt">vs {altType}</span></>
                      ) : (
                        <>{altType} <span className="alt">did not finish</span></>
                      );
                    return (
                      <div className={`v4-feed-row ${r.providerType === 'QPU' ? 'q' : 'c'}`} key={i}>
                        <div className="line1">
                          <span className="type">{r.providerType}</span>
                          <span className="win-t">{fmtSecs(r.solveTime)}</span>
                        </div>
                        <div className="line2">{line2}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="v4-feed-empty">Waiting for the first routing…</div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
