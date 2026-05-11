const SLIDERS = [
  { label: 'Trading activity', val: 'High',       pct: 70 },
  { label: 'Risk preference',  val: 'Aggressive', pct: 78 },
  { label: 'Trade size',       val: 'Medium',     pct: 50 },
  { label: 'Holding style',    val: 'Patient',    pct: 30 },
  { label: 'Diversification',  val: 'Balanced',   pct: 55 },
];

const ASSETS = [
  { id: 'crypto-btc',  ticker: 'BTC',  change: '+2.1%',  cls: 'up' },
  { id: 'crypto-eth',  ticker: 'ETH',  change: '+1.4%',  cls: 'up' },
  { id: 'crypto-sol',  ticker: 'SOL',  change: '+3.0%',  cls: 'up' },
  { id: 'crypto-link', ticker: 'LINK', change: '−0.6%',  cls: 'down' },
  { id: 'crypto-uni',  ticker: 'UNI',  change: '+0.3%',  cls: 'up' },
  { id: 'crypto-usdc', ticker: 'USDC', change: '±0.0%',  cls: 'flat' },
];

export default function StateC() {
  return (
    <div className="bigscreen dir-quipsite v4 state-d">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Welcome · Sign-up · Day 1</span><span className="bar"></span></div>
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
            <label>X handle (optional)</label>
            <div className="sdf-input sdf-input-placeholder">Your handle</div>
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
          <div className="state-d-eyebrow cyan-dot">Supported assets</div>
          <div className="state-d-asset-list">
            {ASSETS.map(a => (
              <div className="sda-row" key={a.ticker}>
                <svg className="sda-glyph" viewBox="0 0 32 32"><use href={`#${a.id}`} /></svg>
                <span className="sda-ticker">{a.ticker}</span>
                <span className={`sda-change ${a.cls}`}>{a.change}</span>
              </div>
            ))}
          </div>
          <div className="state-d-asset-tail">Final basket TBD</div>
        </div>

      </div>
    </div>
  );
}
