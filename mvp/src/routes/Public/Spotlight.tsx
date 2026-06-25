import { assetColor, ASSET_BY_TICKER, type AssetTicker, type LeaderboardEntry } from '../../api';
import { fmtUsd } from '../../utils/format';

// Top-10 spotlight — the #1 agent as a trophy card. P&L / total / holdings come
// from the leaderboard + agent config (real). The allocation bar is DERIVED from
// the agent's chosen assets (weighted by each asset's vol) as an indicative mix
// until a public per-agent weight endpoint exists; widths are normalised to fill.
function deriveAllocation(assets: AssetTicker[]) {
  const weighted = assets.map(t => ({ t, w: ASSET_BY_TICKER[t]?.vol ?? 0.1 }));
  const top = weighted.sort((a, b) => b.w - a.w).slice(0, 6);
  const sum = top.reduce((a, b) => a + b.w, 0) || 1;
  return top.map(x => ({ ticker: x.t, pct: Math.round((x.w / sum) * 100) }));
}

export default function Spotlight({ agent }: { agent: LeaderboardEntry | null }) {
  if (!agent) return null;
  const pos = agent.plPct >= 0;
  const sign = agent.plPct > 0 ? '+' : agent.plPct < 0 ? '−' : '';
  // Assets come from the public leaderboard entry — never a token-gated /agents/{id}
  // fetch (the public page has no owner token, so that would 401 in a loop).
  const alloc = agent.assets && agent.assets.length ? deriveAllocation(agent.assets) : [];

  return (
    <section className="qpub-section qpub-spot" data-reveal>
      <span className="qpub-eyebrow">Top-10 spotlight</span>
      <div className="qpub-spot-card">
        <div className="qpub-spot-lead">
          <span className="qpub-spot-rank">Rank 01 · Leading the floor</span>
          <h3>{agent.name}</h3>
          <div className={`qpub-spot-pnl ${pos ? 'up' : 'dn'}`}>{sign}{Math.abs(agent.plPct).toFixed(2)}%</div>
          <span className="qpub-spot-meta">
            {fmtUsd(agent.total)} · {agent.jobsSolved} jobs solved · {agent.primaryProvider === 'QPU' ? 'quantum-led' : 'classical-led'}
          </span>
        </div>
        <div className="qpub-spot-alloc">
          <span className="qpub-eyebrow sm">Allocation</span>
          {alloc.length ? (
            <>
              <div className="qpub-alloc-bar">
                {alloc.map(a => (
                  <span key={a.ticker} style={{ width: `${a.pct}%`, background: assetColor(a.ticker) }} />
                ))}
              </div>
              <div className="qpub-alloc-key">
                {alloc.map(a => (
                  <span key={a.ticker}><i style={{ background: assetColor(a.ticker) }} />{a.ticker} {a.pct}%</span>
                ))}
              </div>
            </>
          ) : (
            <p className="qpub-spot-noalloc">Holdings revealed once this agent's first rebalance settles.</p>
          )}
        </div>
      </div>
    </section>
  );
}
