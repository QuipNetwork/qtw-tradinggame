import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { submitAgent, requestOptimization, ASSETS, CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc } from '../../api';
import type { SliderValues, AssetTicker, AssetInfo } from '../../api';
import { maxPositionCapPct, rebalanceTierIndex, REBALANCE_CHIP_LABELS, labelFor } from '../../utils/strategy';
import KioskStage from './Stage';
import ResetControl from './ResetControl';

// All three sliders are parameters of the allocation problem the solver runs
// (it allocates the portfolio — it doesn't execute trades): how often to
// re-optimize, how hard to chase returns, and how big any single position
// may get.
const SLIDER_DEFS: Array<{ key: keyof SliderValues; label: string; initial: number }> = [
  // Cadence values are the REAL tiers (QPU time costs money — hourly is the
  // hard cap at the most aggressive setting). See utils/strategy REBALANCE_TIERS.
  // Display labels come from the shared SLIDER_LABELS (via labelFor) so the kiosk
  // and the phone profile never disagree on a slider's wording.
  { key: 'rebalanceFrequency', label: 'Rebalance frequency', initial: 70 },
  { key: 'riskPreference',     label: 'Risk preference',     initial: 78 },
  { key: 'maxPositionSize',    label: 'Max position size',   initial: 50 },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// The watchlist needs at least this many assets so the optimizer can meaningfully
// sub-select (hold at least 3 of them — see the "Number to hold" K slider).
const MIN_ASSETS = 5;

// "Would you like someone from our team to reach out to you?" — verbatim from
// the Luma event registration so kiosk leads and event sign-ups share one
// taxonomy. Captures consent + intent + audience segment in a single question;
// the chip shows a short label, `value` is the full Luma option text stored on
// the agent. "No thanks" is the opt-out and is mutually exclusive with the rest.
// Short gerund chip labels (the question header supplies the "Yes, I'm
// interested in…" framing); `value` is the full Luma option text stored on the
// agent so the kiosk and event taxonomies stay aligned. "No thanks" is the
// explicit opt-out and is mutually exclusive with the rest (see toggleReachOut).
const REACH_OUT_DECLINE = 'No thanks';
const REACH_OUT_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Learning more about quantum computing',         value: "Yes, I'd like to learn more about quantum computing" },
  { label: 'Buying compute',                                value: "Yes, I'm interested in buying compute" },
  { label: 'Providing compute',                             value: "Yes, I'm interested in providing compute" },
  { label: 'Building quantum applications',                 value: "Yes, I'm interested in building quantum applications" },
  { label: 'Partnering with Quip Network',                  value: "Yes, I'm interested in partnering with Quip Network" },
  { label: 'Learning more about post-quantum cryptography', value: "Yes, I'd like to learn more about post-quantum cryptography" },
  { label: 'No thanks',                                     value: REACH_OUT_DECLINE },
];

function handleFromName(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '');
  return '@' + (slug || 'player');
}

export default function KioskSignUp() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [reachOut, setReachOut] = useState<Set<string>>(new Set());
  const [updatesOptIn, setUpdatesOptIn] = useState(false);
  const [updateFrequency, setUpdateFrequency] = useState<'daily' | 'hourly'>('daily');

  function toggleReachOut(value: string) {
    setReachOut(prev => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
        return next;
      }
      // "No thanks" is mutually exclusive with the interest options.
      if (value === REACH_OUT_DECLINE) next.clear();
      else next.delete(REACH_OUT_DECLINE);
      next.add(value);
      return next;
    });
  }
  const [sliders, setSliders] = useState<number[]>(SLIDER_DEFS.map(s => s.initial));
  // Method 3 cardinality: how many of the basket the optimizer holds (K).
  // null ⇒ hold all; clamped to [2, basket size] at launch.
  const [holdCount, setHoldCount] = useState<number | null>(null);
  // Start with an empty basket — the player actively picks their assets.
  const [selected, setSelected] = useState<Set<AssetTicker>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewName = (name.trim() || 'Player');
  const previewHandle = handleFromName(previewName);
  const nameValid = name.trim().length > 0;
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

  // Kiosk reset for the booth attendant: wipe the form back to defaults for the
  // next person. Same route, so this clears state in place (no remount).
  function resetForm() {
    setName('');
    setEmail('');
    setReachOut(new Set());
    setUpdatesOptIn(false);
    setUpdateFrequency('daily');
    setSliders(SLIDER_DEFS.map(s => s.initial));
    setHoldCount(null);
    setSelected(new Set());
    setError(null);
  }

  // Auto-pick: a coin flip per asset builds a random basket (never below the
  // minimum — top up with random distinct assets if the flips came up short).
  function autoPick() {
    const picked = new Set(ASSETS.filter(() => Math.random() < 0.5).map(a => a.ticker));
    while (picked.size < MIN_ASSETS) {
      picked.add(ASSETS[Math.floor(Math.random() * ASSETS.length)].ticker);
    }
    setSelected(picked);
  }

  async function launch() {
    if (busy || selected.size < MIN_ASSETS || !nameValid || !emailValid || reachOut.size === 0) return;
    setBusy(true);
    setError(null);
    const sliderValues = SLIDER_DEFS.reduce<SliderValues>((acc, def, i) => {
      acc[def.key] = sliders[i];
      return acc;
    }, {} as SliderValues);
    // K (Method 3): hold the best K of the watchlist; default = hold all.
    sliderValues.holdCount = Math.max(3, Math.min(holdCount ?? selected.size, selected.size));
    try {
      const { agentId, qrUrl } = await submitAgent({
        name: previewName,
        handle: previewHandle,
        email: email.trim(),
        reachOut: reachOut.size ? REACH_OUT_OPTIONS.filter(o => reachOut.has(o.value)).map(o => o.value) : undefined,
        updatesOptIn,
        updateFrequency: updatesOptIn ? updateFrequency : undefined,
        sliders: sliderValues,
        assets: ASSETS.filter(a => selected.has(a.ticker)).map(a => a.ticker),
      });
      // The agent now exists — persist it and move on, so a failed first solve
      // can't strand the attendee here or let a re-press create a duplicate
      // agent. The first solve is best-effort caching; the welcome screen
      // re-solves on its own if it's missing.
      localStorage.setItem('quip:lastAgentId', agentId);
      sessionStorage.setItem('quip:qrUrl:' + agentId, qrUrl);
      try {
        const result = await requestOptimization(agentId);
        sessionStorage.setItem('quip:lastResult:' + agentId, JSON.stringify(result));
      } catch {
        // Leave it to the welcome screen to solve and surface any error.
      }
      navigate(`/kiosk/welcome?agent=${agentId}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create your agent. Check the backend connection.');
    } finally {
      setBusy(false);
    }
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

  const detailsCard = (
    <div className="v4m-mega">
      <div className="v4m-mega-section">
        <span className="v4m-section-eyebrow eyebrow-step" role="heading" aria-level={2}><span className="v4m-step-chip" aria-hidden="true">3</span>Your details</span>
        <div className="v4m-field">
          <label htmlFor="kiosk-name">Player name (required)</label>
          <input
            className="v4m-input"
            id="kiosk-name"
            type="text"
            value={name}
            placeholder="Your name"
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
          <div className="v4m-field-hint">So we can reach you if you win</div>
        </div>
        <button
          type="button"
          className={`v4m-check-row v4m-optin-row${updatesOptIn ? ' on' : ''}`}
          aria-pressed={updatesOptIn}
          onClick={() => setUpdatesOptIn(v => !v)}
        >
          <span className="v4m-check-box" aria-hidden="true">{updatesOptIn ? '✓' : ''}</span>
          <span className="v4m-check-label">Email me my portfolio results</span>
        </button>
        {updatesOptIn && (
          <div className="v4m-freq" role="group" aria-label="Email frequency">
            {(['hourly', 'daily'] as const).map(f => (
              <button
                type="button"
                key={f}
                className={`v4m-freq-opt${updateFrequency === f ? ' on' : ''}`}
                aria-pressed={updateFrequency === f}
                onClick={() => setUpdateFrequency(f)}
              >
                {f === 'daily' ? 'End of day' : 'By hour'}
              </button>
            ))}
          </div>
        )}
        <div className="v4m-field v4m-field-checklist">
          <label>Would you like someone from our team to reach out?<span className="lead">Yes, I'm interested in…<span className="req" aria-hidden="true">*</span></span></label>
          <div className="v4m-checklist" role="group" aria-label="Would you like someone from our team to reach out?">
            {REACH_OUT_OPTIONS.map(o => (
              <button
                type="button"
                key={o.value}
                className={`v4m-check-row${reachOut.has(o.value) ? ' on' : ''}`}
                aria-pressed={reachOut.has(o.value)}
                onClick={() => toggleReachOut(o.value)}
              >
                <span className="v4m-check-box" aria-hidden="true">{reachOut.has(o.value) ? '✓' : ''}</span>
                <span className="v4m-check-label">{o.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <KioskStage>
    <div className="qs-v4-mock kiosk-v4 app-fit">

      <div className="v4m-nav">
        <div className="v4m-mark">
          <svg className="quip-wm" role="img" aria-label="Quip Network"><use href="#quip-wm" /></svg>
          <div className="v4m-nav-divider"></div>
          <span className="v4m-eyebrow">Quantum.Tech World 2026 · Trading Competition</span>
        </div>
        <span className="v4m-pill">Live · Sign-up</span>
      </div>

      <div className="v4m-hero">
        <h1>Create your <span className="it">quantum</span> trading agent.</h1>
        <ResetControl onConfirm={resetForm} />
      </div>

      <main className="v4m-body selector-top">

        <div className="v4m-main-col">

          <div className="v4m-mega v4m-selector-mega" aria-label="Asset selector">
            <div className="v4m-mega-section v4m-selector-section">
              <div className="v4m-selector-head">
                <span className="v4m-section-eyebrow eyebrow-step" role="heading" aria-level={2}><span className="v4m-step-chip" aria-hidden="true">1</span>Pick your watchlist <span className="v4m-selector-req">· min {MIN_ASSETS}</span></span>
                <span className={`v4m-selector-count${selected.size > 0 && selected.size < MIN_ASSETS ? ' under' : ''}`}>{selected.size}/{ASSETS.length}</span>
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
                <span className="v4m-section-eyebrow eyebrow-step" role="heading" aria-level={2}><span className="v4m-step-chip" aria-hidden="true">2</span>Tune your strategy</span>
              </div>
              <div className="v4m-sliders-row">
                {SLIDER_DEFS.map((def, i) =>
                  def.key === 'rebalanceFrequency' ? null : (
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
                          aria-label={def.label}
                          aria-valuetext={labelFor(i, sliders[i])}
                          onChange={e => updateSlider(i, parseInt(e.target.value, 10))}
                        />
                      </div>
                      <div className="v4m-slider-bottom">
                        <span className="v4m-slider-val">
                          {labelFor(i, sliders[i])}
                          {/* the position cap is relative to the basket — show the live number */}
                          {def.key === 'maxPositionSize' && selected.size > 0 && ` · ≤${maxPositionCapPct(selected.size, sliders[i])}%`}
                        </span>
                      </div>
                    </div>
                  )
                )}
                {/* Number to hold (K) — the third slider; a count tied to the basket
                    (the optimizer sub-selects the best K). Disabled until ≥2 picked. */}
                {(() => {
                  const n = selected.size;
                  const ready = n >= 3;
                  const k = ready ? Math.max(3, Math.min(holdCount ?? n, n)) : 3;
                  const pct = ready ? (n > 3 ? ((k - 3) / (n - 3)) * 100 : 100) : 0;
                  return (
                    <div className={`v4m-slider${ready ? '' : ' disabled'}`} key="holdCount">
                      <div className="v4m-slider-top">
                        <span className="v4m-slider-label">Number to hold</span>
                      </div>
                      <div className="v4m-slider-shell">
                        <div className="v4m-slider-track">
                          <div className="v4m-slider-fill" style={{ width: `${pct}%` }}></div>
                          <div className="v4m-slider-knob" style={{ left: `${pct}%` }}></div>
                        </div>
                        <input
                          type="range"
                          className="range-overlay"
                          min={3}
                          max={Math.max(3, n)}
                          step={1}
                          value={k}
                          aria-label="Number to hold"
                          aria-valuetext={ready ? `${k} of ${n}` : 'Pick a watchlist first'}
                          disabled={!ready}
                          onChange={e => setHoldCount(parseInt(e.target.value, 10))}
                        />
                      </div>
                      <div className="v4m-slider-bottom">
                        <span className="v4m-slider-val">
                          {ready ? `${k} of ${n}${k === n ? ' · all' : ''}` : 'pick a watchlist first'}
                        </span>
                      </div>
                    </div>
                  );
                })()}
              </div>
              {/* Rebalance cadence — discrete tiers as a COMPACT inline row (label +
                  chips on one line) so the card stays short and the watchlist
                  above doesn't scroll. */}
              <div className="v4m-cadence">
                <span className="v4m-cadence-label">Rebalance</span>
                <div className="v4m-cad-row">
                  {REBALANCE_CHIP_LABELS.map((lbl, t) => {
                    const active = rebalanceTierIndex(sliders[0]) === t;
                    return (
                      <button
                        type="button"
                        key={lbl}
                        className={`v4m-cad-chip${active ? ' on' : ''}`}
                        aria-pressed={active}
                        onClick={() => updateSlider(0, t * 25)}
                      >
                        {lbl}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

        </div>

        <aside className="v4m-rail-col" aria-label="Your details">
          {detailsCard}
        </aside>

      </main>

      <div className="v4m-cta-bar">
        <button className={`v4m-cta${busy ? ' busy' : ''}`} onClick={launch} disabled={busy || selected.size < MIN_ASSETS || !nameValid || !emailValid || reachOut.size === 0}>
          <span className="v4m-cta-label"><span className="v4m-step-chip cta">4</span>{busy ? 'Routing through Quip…' : 'Create your agent'}</span>
          <span className="v4m-cta-arrow">→</span>
        </button>
        {(() => {
          const blocked = error
            ? error
            : selected.size < MIN_ASSETS
              ? `Select at least ${MIN_ASSETS} assets to launch`
              : !nameValid
                ? 'Enter a player name to launch'
                : !emailValid
                  ? 'Enter your email to launch'
                  : reachOut.size === 0
                    ? 'Choose a reach-out preference (or “No thanks”) to launch'
                    : null;
          return (
            <div className={`v4m-cta-sub${blocked ? '' : ' ok'}`} role="status">
              {blocked ?? 'All set — ready to launch'}
            </div>
          );
        })()}
      </div>

    </div>
    </KioskStage>
  );
}
