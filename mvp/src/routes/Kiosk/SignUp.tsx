import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { submitAgent, requestOptimization, ASSETS, CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc } from '../../api';
import type { SliderValues, AssetTicker, AssetInfo } from '../../api';
import { maxPositionCapPct } from '../../utils/strategy';
import KioskStage from './Stage';

// All three sliders are parameters of the allocation problem the solver runs
// (it allocates the portfolio — it doesn't execute trades): how often to
// re-optimize, how hard to chase returns, and how big any single position
// may get.
const SLIDER_DEFS: Array<{ key: keyof SliderValues; label: string; initial: number; labels: [string, string, string, string, string] }> = [
  // Cadence values are the REAL tiers (QPU time costs money — hourly is the
  // hard cap at the most aggressive setting). See utils/strategy REBALANCE_TIERS.
  { key: 'rebalanceFrequency', label: 'Rebalance frequency', initial: 70, labels: ['Daily', 'Every 8h', 'Every 4h', 'Every 2h', 'Hourly'] },
  { key: 'riskPreference',     label: 'Risk preference',     initial: 78, labels: ['Safe', 'Conservative', 'Balanced', 'Aggressive', 'Reckless'] },
  { key: 'maxPositionSize',    label: 'Max position size',   initial: 50, labels: ['Tiny', 'Small', 'Medium', 'Large', 'Heavy'] },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// "Would you like someone from our team to reach out to you?" — verbatim from
// the Luma event registration so kiosk leads and event sign-ups share one
// taxonomy. Captures consent + intent + audience segment in a single question;
// the chip shows a short label, `value` is the full Luma option text stored on
// the agent. "No thanks" is the opt-out and is mutually exclusive with the rest.
// Short chip labels (the question header supplies the "Yes, I'm interested
// in…" framing); `value` is the full Luma option text stored on the agent.
const REACH_OUT_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Learn about quantum computing',   value: "Yes, I'd like to learn more about quantum computing" },
  { label: 'Buying compute',                  value: "Yes, I'm interested in buying compute" },
  { label: 'Providing compute',               value: "Yes, I'm interested in providing compute" },
  { label: 'Building quantum applications',   value: "Yes, I'm interested in building quantum applications" },
  { label: 'Partnering with Quip Network',    value: "Yes, I'm interested in partnering with Quip Network" },
  { label: 'Post-quantum cryptography',       value: "Yes, I'd like to learn more about post-quantum cryptography" },
  { label: 'No thanks',                       value: 'No thanks' },
];
const NO_THANKS = 'No thanks';

function labelFor(value: number, labels: readonly string[]): string {
  const i = Math.min(labels.length - 1, Math.floor(value / 20));
  return labels[i];
}

function handleFromName(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '');
  return '@' + (slug || 'player');
}

export default function KioskSignUp() {
  const navigate = useNavigate();
  const [name, setName] = useState('Lattice Theory');
  const [email, setEmail] = useState('');
  const [reachOut, setReachOut] = useState<Set<string>>(new Set());

  // "No thanks" is mutually exclusive with the affirmative options.
  function toggleReachOut(value: string) {
    setReachOut(prev => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
      } else if (value === NO_THANKS) {
        return new Set([NO_THANKS]);
      } else {
        next.delete(NO_THANKS);
        next.add(value);
      }
      return next;
    });
  }
  const [sliders, setSliders] = useState<number[]>(SLIDER_DEFS.map(s => s.initial));
  const [selected, setSelected] = useState<Set<AssetTicker>>(new Set(ASSETS.map(a => a.ticker)));
  const [busy, setBusy] = useState(false);

  const previewName = (name.trim() || 'Player');
  const previewHandle = handleFromName(previewName);
  const emailValid = EMAIL_RE.test(email.trim());

  function updateSlider(i: number, v: number) {
    setSliders(prev => {
      const next = [...prev];
      next[i] = v;
      return next;
    });
  }

  function toggleAsset(ticker: AssetTicker) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(ASSETS.map(a => a.ticker)));
  }

  function selectNone() {
    setSelected(new Set());
  }

  // Auto-pick: a coin flip per asset builds a random basket (never empty).
  function autoPick() {
    const picked = ASSETS.filter(() => Math.random() < 0.5).map(a => a.ticker);
    if (picked.length === 0) {
      picked.push(ASSETS[Math.floor(Math.random() * ASSETS.length)].ticker);
    }
    setSelected(new Set(picked));
  }

  async function launch() {
    if (busy || selected.size === 0 || !emailValid) return;
    setBusy(true);
    const sliderValues = SLIDER_DEFS.reduce<SliderValues>((acc, def, i) => {
      acc[def.key] = sliders[i];
      return acc;
    }, {} as SliderValues);
    const { agentId } = await submitAgent({
      name: previewName,
      handle: previewHandle,
      email: email.trim(),
      reachOut: reachOut.size ? REACH_OUT_OPTIONS.filter(o => reachOut.has(o.value)).map(o => o.value) : undefined,
      sliders: sliderValues,
      assets: ASSETS.filter(a => selected.has(a.ticker)).map(a => a.ticker),
    });
    const result = await requestOptimization(agentId);
    sessionStorage.setItem('quip:lastResult:' + agentId, JSON.stringify(result));
    navigate(`/kiosk/welcome?agent=${agentId}`);
  }

  function renderAssetTile(asset: AssetInfo) {
    const on = selected.has(asset.ticker);
    return (
      <button
        type="button"
        className={`v4m-tile ${asset.class}${on ? ' on' : ''}`}
        key={asset.ticker}
        onClick={() => toggleAsset(asset.ticker)}
        aria-pressed={on}
      >
        <span className="v4m-tile-check" aria-hidden="true">✓</span>
        <img className="v4m-tile-icon" src={assetIconSrc(asset.ticker)} alt="" loading="lazy" />
        <span className="v4m-tile-ticker">{asset.ticker}</span>
        <span className="v4m-tile-name">{asset.name}</span>
      </button>
    );
  }

  return (
    <KioskStage>
    <div className="qs-v4-mock kiosk-v4 app-fit">

      <div className="v4m-nav">
        <div className="v4m-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="v4m-nav-divider"></div>
          <span className="v4m-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <span className="v4m-pill">Live · Sign-up · Day 1</span>
      </div>

      <div className="v4m-hero">
        <h1>Create your <span className="it">trading agent.</span></h1>
      </div>

      <div className="v4m-body selector-top">

        <div className="v4m-main-col">

          <div className="v4m-mega v4m-selector-mega" aria-label="Asset selector">
            <div className="v4m-mega-section v4m-selector-section">
              <div className="v4m-selector-head">
                <span className="v4m-section-eyebrow eyebrow-step"><span className="v4m-step-chip">1</span>Pick your basket</span>
                <span className="v4m-selector-count">{selected.size}/{ASSETS.length}</span>
              </div>
              <div className="v4m-selector-actions">
                <button type="button" className="v4m-selector-btn" onClick={selectAll}>All</button>
                <button type="button" className="v4m-selector-btn" onClick={selectNone}>Clear</button>
                <button type="button" className="v4m-selector-btn accent" onClick={autoPick}>Auto-pick</button>
              </div>
              <div className="v4m-pick-list">
                <div className="v4m-pick-group-label">Crypto · {CRYPTO_ASSETS.length}</div>
                <div className="v4m-pick-grid">{CRYPTO_ASSETS.map(renderAssetTile)}</div>
                <div className="v4m-pick-group-label">Stocks · {STOCK_ASSETS.length}</div>
                <div className="v4m-pick-grid">{STOCK_ASSETS.map(renderAssetTile)}</div>
              </div>
            </div>
          </div>

          <div className="v4m-mega v4m-sliders-mega" aria-label="Strategy sliders">
            <div className="v4m-mega-section">
              <div className="v4m-sliders-head">
                <span className="v4m-section-eyebrow eyebrow-step"><span className="v4m-step-chip">2</span>Tune your strategy</span>
              </div>
              <div className="v4m-sliders-row">
                {SLIDER_DEFS.map((def, i) => (
                  <div className="v4m-slider" key={def.key}>
                    <div className="v4m-slider-top">
                      <span className="v4m-slider-label">{def.label}</span>
                    </div>
                    <div className="v4m-slider-shell">
                      <div className="v4m-slider-track">
                        <div className="v4m-slider-fill" style={{ width: `${sliders[i]}%` }}></div>
                        <div className="v4m-slider-knob" style={{ left: `${sliders[i]}%` }}></div>
                      </div>
                      <input
                        type="range"
                        className="range-overlay"
                        min={0}
                        max={100}
                        value={sliders[i]}
                        onChange={e => updateSlider(i, parseInt(e.target.value, 10))}
                      />
                    </div>
                    <div className="v4m-slider-bottom">
                      <span className="v4m-slider-val">
                        {labelFor(sliders[i], def.labels)}
                        {/* the position cap is relative to the basket — show the live number */}
                        {def.key === 'maxPositionSize' && selected.size > 0 && ` · ≤${maxPositionCapPct(selected.size, sliders[i])}%`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

        </div>

        <aside className="v4m-rail-col" aria-label="Your details and agent">
          {/* Step 3 — player details, its own card */}
          <div className="v4m-mega">
            <div className="v4m-mega-section">
              <span className="v4m-section-eyebrow eyebrow-step"><span className="v4m-step-chip">3</span>Your details</span>
              <div className="v4m-field">
                <label htmlFor="kiosk-name">Player name</label>
                <input
                  className="v4m-input"
                  id="kiosk-name"
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                />
              </div>
              <div className="v4m-field">
                <label htmlFor="kiosk-email">Email (required)</label>
                <input
                  className="v4m-input"
                  id="kiosk-email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                />
              </div>
              <div className="v4m-field v4m-field-chips">
                <label>Would you like someone from our team to reach out? (optional)</label>
                <div className="v4m-chips v4m-chips-grid">
                  {REACH_OUT_OPTIONS.map(o => (
                    <button
                      type="button"
                      key={o.value}
                      className={`v4m-chip${reachOut.has(o.value) ? ' on' : ''}${o.value === NO_THANKS ? ' v4m-chip-muted' : ''}`}
                      aria-pressed={reachOut.has(o.value)}
                      onClick={() => toggleReachOut(o.value)}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Agent preview — separate card */}
          <div className="v4m-mega">
            <div className="v4m-mega-section">
              <span className="v4m-section-eyebrow cyan-dot">Your Agent</span>
              <div className="v4m-preview v4m-preview-mystery">
                <div className="v4m-preview-mystery-box" aria-hidden="true">
                  <svg className="v4m-preview-butterfly" viewBox="219 4 106 103" xmlns="http://www.w3.org/2000/svg">
                    <use href="#quip-butterfly" />
                  </svg>
                </div>
                <div className="v4m-preview-name">{previewName}</div>
                <div className="v4m-preview-handle">{previewHandle}</div>
                <div className="v4m-preview-mystery-caption">Identity revealed at launch</div>
              </div>
            </div>
          </div>
        </aside>

      </div>

      <div className="v4m-cta-bar">
        <button className={`v4m-cta${busy ? ' busy' : ''}`} onClick={launch} disabled={busy || selected.size === 0 || !emailValid}>
          <span className="v4m-cta-label"><span className="v4m-step-chip cta">4</span>{busy ? 'Routing through Quip…' : 'Create your agent'}</span>
          <span className="v4m-cta-arrow">→</span>
        </button>
        <div className="v4m-cta-sub">
          {selected.size === 0
            ? 'Select at least one asset to launch'
            : !emailValid
              ? 'Enter your email to launch'
              : `${selected.size} asset${selected.size === 1 ? '' : 's'} in basket · Your unique identity is revealed once you launch · ~1 second to first job`}
        </div>
      </div>

    </div>
    </KioskStage>
  );
}
