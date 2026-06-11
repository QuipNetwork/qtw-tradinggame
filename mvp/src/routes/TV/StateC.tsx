import { CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc } from '../../api';
import type { AssetInfo } from '../../api';

const SLIDERS = [
  { label: 'Rebalance frequency', val: 'Every 2h',   pct: 70 },
  { label: 'Risk preference',     val: 'Aggressive', pct: 78 },
  { label: 'Max position size',   val: 'Medium',     pct: 50 },
];

// Deterministic fake 24h change per ticker (demo data — no live feed on TV).
function fakeChange(ticker: string): { text: string; cls: string } {
  let h = 0;
  for (let i = 0; i < ticker.length; i++) h = (h * 31 + ticker.charCodeAt(i)) >>> 0;
  const v = ((h % 61) - 28) / 10;   // −2.8 … +3.2
  if (Math.abs(v) < 0.05) return { text: '±0.0%', cls: 'flat' };
  return { text: `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`, cls: v > 0 ? 'up' : 'down' };
}

function assetRow(a: AssetInfo) {
  const c = fakeChange(a.ticker);
  return (
    <div className="sda-row" key={a.ticker}>
      <img className="sda-glyph" src={assetIconSrc(a.ticker)} alt="" />
      <span className="sda-ticker">{a.ticker}</span>
      <span className={`sda-change ${c.cls}`}>{c.text}</span>
    </div>
  );
}

export default function StateC() {
  return (
    <div className="bigscreen dir-quipsite v4 state-d">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Welcome · Sign-up</span><span className="bar"></span></div>
      </div>

      <div className="state-d-body">

        <div className="state-d-intro">
          <div className="state-d-eyebrow">What's happening here</div>
          <h1>Quantum trading, <span className="it">live.</span></h1>
          <p>Attendees build trading agents at the booth kiosk — name, strategy, $10K virtual bankroll — and deploy them onto the leaderboard.</p>
          <p>Every order routes through Quip Network. Quantum and classical solvers race in parallel; the fastest valid optimum wins the job.</p>
          <p>Live P&amp;L tracked across the conference. Climb the board, retune anytime. <strong>Top 10 win prizes.</strong></p>
          <div className="state-d-legend">
            <div className="sdl-row"><span className="sdl-tag">Real</span><span className="sdl-val">Market signals</span></div>
            <div className="sdl-row fake"><span className="sdl-tag">Fake</span><span className="sdl-val">Money at risk</span></div>
            <div className="sdl-row live"><span className="sdl-tag">Live</span><span className="sdl-val">Quantum routing</span></div>
          </div>
        </div>

        <div className="state-d-form">
          <div className="state-d-eyebrow">Create your agent</div>
          <h2 className="state-d-form-title">Create your <span className="it">trading agent.</span></h2>

          <div className="sdf-field">
            <label>Player name</label>
            <div className="sdf-input sdf-input-placeholder">Your name</div>
          </div>
          <div className="sdf-field">
            <label>Email (required)</label>
            <div className="sdf-input sdf-input-placeholder">you@example.com</div>
          </div>

          {SLIDERS.map(s => (
            <div className="sdf-slider" key={s.label}>
              <div className="sdf-slider-top"><span className="sdf-label">{s.label}</span><span className="sdf-val">{s.val}</span></div>
              <div className="sdf-track">
                <div className="sdf-fill" style={{ width: `${s.pct}%` }}></div>
                <div className="sdf-knob" style={{ left: `${s.pct}%` }}></div>
              </div>
            </div>
          ))}

        </div>

        <div className="state-d-assets">
          <div className="state-d-eyebrow cyan-dot">Supported assets · 25</div>
          <div className="state-d-asset-list all">
            <div className="sda-col">
              <div className="sda-col-head">Crypto · {CRYPTO_ASSETS.length}</div>
              {CRYPTO_ASSETS.map(assetRow)}
            </div>
            <div className="sda-col">
              <div className="sda-col-head">Stocks · {STOCK_ASSETS.length}</div>
              {STOCK_ASSETS.map(assetRow)}
            </div>
          </div>
          <div className="state-d-asset-tail">Pick your basket at the kiosk</div>
        </div>

      </div>
    </div>
  );
}
