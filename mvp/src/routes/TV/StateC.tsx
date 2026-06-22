import { useEffect, useState } from 'react';
import { CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc } from '../../api';
import type { AssetInfo } from '../../api';

const SLIDERS = [
  { label: 'Rebalance frequency', val: 'Every 2h',   pct: 70 },
  { label: 'Risk preference',     val: 'Aggressive', pct: 78 },
  { label: 'Max position size',   val: 'Medium',     pct: 50 },
];

const ALL_ASSETS = [...CRYPTO_ASSETS, ...STOCK_ASSETS];

// Deterministic seed for each ticker's starting 24h change (the TV has no live
// per-asset feed); the values then drift gently so the list feels alive.
function seededChange(ticker: string): number {
  let h = 0;
  for (let i = 0; i < ticker.length; i++) h = (h * 31 + ticker.charCodeAt(i)) >>> 0;
  return ((h % 61) - 28) / 10;   // −2.8 … +3.2
}

function formatChange(v: number): { text: string; cls: string } {
  if (Math.abs(v) < 0.05) return { text: '±0.0%', cls: 'flat' };
  return { text: `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`, cls: v > 0 ? 'up' : 'down' };
}

export default function StateC() {
  const [changes, setChanges] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {};
    for (const a of ALL_ASSETS) init[a.ticker] = seededChange(a.ticker);
    return init;
  });

  // Gently drift each asset's change while this state is on screen, so the
  // supported-assets list reads as a live market rather than a frozen mock.
  useEffect(() => {
    const id = window.setInterval(() => {
      setChanges(prev => {
        const next: Record<string, number> = {};
        for (const ticker of Object.keys(prev)) {
          const drift = (Math.random() - 0.5) * 0.4;
          next[ticker] = Math.max(-6, Math.min(7, prev[ticker] + drift));
        }
        return next;
      });
    }, 2000);
    return () => window.clearInterval(id);
  }, []);

  const assetRow = (a: AssetInfo) => {
    const c = formatChange(changes[a.ticker] ?? 0);
    return (
      <div className="sda-row" key={a.ticker}>
        <img className="sda-glyph" src={assetIconSrc(a.ticker)} alt="" />
        <span className="sda-ticker">{a.ticker}</span>
        <span className={`sda-change ${c.cls}`}>{c.text}</span>
      </div>
    );
  };

  return (
    <div className="bigscreen dir-quipsite v4 state-d">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum.Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Welcome · Sign-up</span><span className="bar"></span></div>
      </div>

      <div className="state-d-body">

        <div className="state-d-intro">
          <div className="state-d-eyebrow">What's happening here</div>
          <h1><span className="it">Quantum</span> trading, live.</h1>
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
          <div className="state-d-eyebrow cyan-dot">Supported assets · {CRYPTO_ASSETS.length + STOCK_ASSETS.length}</div>
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
