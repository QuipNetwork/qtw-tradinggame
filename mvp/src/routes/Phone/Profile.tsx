import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import type { AgentConfig, AgentUpdate, RoutingResult, SliderValues, AssetTicker, AssetInfo } from '../../api';
import { getAgent, requestOptimization, subscribeAgent, updateAgent, ASSETS, CRYPTO_ASSETS, STOCK_ASSETS, assetIconSrc } from '../../api';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';
import { glyphParams, labelFor, slidersToArray } from '../../utils/strategy';

const SLIDER_DEFS: Array<{ key: keyof SliderValues; label: string }> = [
  { key: 'rebalanceFrequency', label: 'Rebalance frequency' },
  { key: 'riskPreference',     label: 'Risk preference' },
  { key: 'maxPositionSize',    label: 'Max position size' },
];

// A basket needs at least this many assets (mirrors the kiosk sign-up rule).
const MIN_ASSETS = 3;

export default function PhoneProfile() {
  const { agentId } = useParams();
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [sliders, setSliders] = useState<number[] | null>(null);
  const [result, setResult] = useState<RoutingResult | null>(null);
  const [live, setLive] = useState<AgentUpdate | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<'profile' | 'basket'>('profile');
  const [basket, setBasket] = useState<Set<AssetTicker>>(new Set());
  const [savingBasket, setSavingBasket] = useState(false);
  const glyphRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!agentId) return;
    (async () => {
      const a = await getAgent(agentId);
      if (!a) return;
      setAgent(a);
      setSliders(slidersToArray(a.sliders));
      setBasket(new Set(a.assets ?? []));

      const cachedRaw = sessionStorage.getItem('quip:lastResult:' + agentId);
      if (cachedRaw) {
        try { setResult(JSON.parse(cachedRaw)); } catch { /* ignore */ }
      }
    })();
  }, [agentId]);

  useEffect(() => {
    if (!agentId) return;
    return subscribeAgent(agentId, setLive);
  }, [agentId]);

  useEffect(() => {
    if (!agent || !glyphRef.current) return;
    const seed = strHash(agent.name);
    const style = pickStyle(seed);
    renderGlyph(glyphRef.current, Object.assign({
      seed,
      ...glyphParams(agent.sliders),
      cell: 3,
    }, style));
  }, [agent]);

  if (!agentId) return <div style={{ padding: 40 }}>Missing agent.</div>;
  if (!agent || !sliders) return null;

  async function retune() {
    if (busy || !agentId || !sliders) return;
    setBusy(true);
    const next: SliderValues = SLIDER_DEFS.reduce<SliderValues>((acc, def, i) => {
      acc[def.key] = sliders[i];
      return acc;
    }, {} as SliderValues);
    setAgent(prev => prev ? { ...prev, sliders: next } : prev);
    const r = await requestOptimization(agentId);
    setResult(r);
    sessionStorage.setItem('quip:lastResult:' + agentId, JSON.stringify(r));
    setBusy(false);
  }

  function toggleBasket(ticker: AssetTicker) {
    setBasket(prev => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  // Save only persists the basket and returns to the profile. Re-optimizing is
  // a separate, explicit action from the main profile ("Re-optimize on Quip").
  async function saveBasket() {
    if (savingBasket || !agentId || basket.size < MIN_ASSETS) return;
    setSavingBasket(true);
    const assets = ASSETS.filter(a => basket.has(a.ticker)).map(a => a.ticker);
    await updateAgent(agentId, { assets });
    setAgent(prev => prev ? { ...prev, assets } : prev);
    setSavingBasket(false);
    setView('profile');
  }

  const basketTile = (a: AssetInfo) => {
    const on = basket.has(a.ticker);
    return (
      <button
        type="button"
        key={a.ticker}
        className={`v4m-tile ${a.class}${on ? ' on' : ''}`}
        aria-pressed={on}
        onClick={() => toggleBasket(a.ticker)}
      >
        <span className="v4m-tile-check" aria-hidden="true">✓</span>
        <img className="v4m-tile-icon" src={assetIconSrc(a.ticker)} alt="" loading="lazy" />
        <span className="v4m-tile-ticker">{a.ticker}</span>
        <span className="v4m-tile-name">{a.name}</span>
      </button>
    );
  };

  const total = live?.total ?? 10142;
  const plUSD = live?.plUSD ?? 142;
  const plPct = live?.plPct ?? 1.42;
  const positive = plUSD >= 0;
  const lineColor = positive ? '#0A832E' : '#ff6467';

  const isQpu = result?.providerType === 'QPU';
  const solveTime = result?.solveTime ?? 0.42;
  const classicalTime = result ? Math.max(solveTime * result.vsClassical, solveTime + 0.1) : 5.88;
  const qBarPct = isQpu ? Math.max(4, (solveTime / classicalTime) * 100) : 100;
  const cBarPct = isQpu ? 100 : Math.max(4, (classicalTime / solveTime) * 100);
  const providerName = result?.provider ?? 'D-Wave Advantage';
  const providerShort = providerName.split(' ')[0];

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#0a0a10', padding: 16 }}>
      <div className="mockup-frame phone dark">
        <div className="screen">
          <div className="qs-v4-mock phone-v4">

            <div className="v4m-status">
              <span>9:41</span>
              <div className="v4m-status-icons">
                <span className="v4m-bars"><span></span><span></span><span></span><span></span></span>
                <span style={{ fontFamily: "'JetBrains Mono',ui-monospace,monospace", fontSize: '0.6rem', letterSpacing: '0.04em' }}>5G</span>
                <span className="v4m-battery"></span>
              </div>
            </div>

            {view === 'basket' ? (
            <div className="v4m-basket-screen">
              <div className="v4m-basket-head">
                <button type="button" className="v4m-basket-back" onClick={() => setView('profile')} aria-label="Back to profile">←</button>
                <span className="v4m-section-eyebrow">Edit basket</span>
                <span className={`v4m-basket-count${basket.size > 0 && basket.size < MIN_ASSETS ? ' under' : ''}`}>{basket.size}/{ASSETS.length} · min {MIN_ASSETS}</span>
              </div>
              <div className="v4m-basket-scroll">
                <div className="v4m-basket-group">Crypto · {CRYPTO_ASSETS.length}</div>
                <div className="v4m-basket-grid">{CRYPTO_ASSETS.map(basketTile)}</div>
                <div className="v4m-basket-group">Stocks · {STOCK_ASSETS.length}</div>
                <div className="v4m-basket-grid">{STOCK_ASSETS.map(basketTile)}</div>
              </div>
              <button className={`v4m-cta${savingBasket ? ' busy' : ''}`} onClick={saveBasket} disabled={savingBasket || basket.size < MIN_ASSETS}>
                <span>{savingBasket ? 'Saving…' : 'Save basket'}</span>
                <span className="v4m-cta-arrow">→</span>
              </button>
              {basket.size < MIN_ASSETS && <div className="v4m-cta-sub">Select at least {MIN_ASSETS} assets</div>}
            </div>
            ) : (
            <div className="v4m-phone-view">

            <div className="v4m-phone-head">
              <div>
                <div className="v4m-phone-name">{agent.name}</div>
              </div>
              <canvas ref={glyphRef} width={56} height={56}></canvas>
              <div className="v4m-phone-rank" style={{ gridColumn: '1 / 3', marginTop: 4, justifySelf: 'start' }}>
                <span>You're</span>
                <span className="v4m-rank-num">#6</span>
                <span>of 247</span>
              </div>
            </div>

            <div className="v4m-pl">
              <div>
                <div className="v4m-section-eyebrow">Total · Live</div>
                <div className="v4m-pl-num">${total.toLocaleString()}</div>
                <div className={`v4m-pl-change ${positive ? 'up' : 'down'}`}>
                  {positive ? '+' : '−'}${Math.abs(plUSD).toLocaleString()} · {positive ? '+' : '−'}{Math.abs(plPct).toFixed(2)}%
                </div>
              </div>
              <svg className="v4m-spark" viewBox="0 0 80 36" preserveAspectRatio="none" aria-hidden="true" style={{ color: lineColor }}>
                <polyline
                  points={positive
                    ? '0,32 8,30 14,28 20,26 28,24 36,18 42,21 48,16 54,14 60,11 68,12 76,7'
                    : '0,8 8,10 14,14 20,16 28,18 36,22 42,21 48,26 54,28 60,30 68,29 76,33'}
                  fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                />
              </svg>
            </div>

            <div className="v4m-phone-mega">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span className="v4m-section-eyebrow cyan-dot cyan">Solved via Quip · 4m ago</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
                <div>
                  <div className="v4m-phone-mega-hero">{providerName}</div>
                  <div className="v4m-phone-mega-meta">
                    {isQpu ? 'Quantum' : 'Classical'} · {result?.vsClassical ?? 14}× vs classical
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: "Georgia, 'Times New Roman', serif", fontStyle: 'italic', fontSize: '1.6rem', letterSpacing: '-0.025em', color: '#0891B2', lineHeight: 1 }}>
                    {solveTime.toFixed(2)}s
                  </div>
                </div>
              </div>
              <div className="v4m-race-block" style={{ borderTop: '1px solid #ececef', paddingTop: 8 }}>
                <div className="v4m-race-row" style={{ gridTemplateColumns: '70px 1fr 50px' }}>
                  <span className="v4m-race-label q">{providerShort}</span>
                  <div className="v4m-race-bar"><div className="v4m-race-fill q" style={{ width: `${qBarPct}%` }}></div></div>
                  <span className="v4m-race-time">{(isQpu ? solveTime : classicalTime).toFixed(2)}s</span>
                </div>
                <div className="v4m-race-row" style={{ gridTemplateColumns: '70px 1fr 50px' }}>
                  <span className="v4m-race-label">Classical</span>
                  <div className="v4m-race-bar"><div className="v4m-race-fill" style={{ width: `${cBarPct}%` }}></div></div>
                  <span className="v4m-race-time">{(isQpu ? classicalTime : solveTime).toFixed(2)}s</span>
                </div>
              </div>
            </div>

            <button type="button" className="v4m-basket-open" onClick={() => setView('basket')}>
              <span className="v4m-section-eyebrow">Your basket · {basket.size} asset{basket.size === 1 ? '' : 's'}</span>
              <span className="v4m-basket-open-cta">Edit →</span>
            </button>

            <div>
              <div className="v4m-section-eyebrow" style={{ marginBottom: 8 }}>Strategy · Drag to Retune</div>
              {SLIDER_DEFS.map((def, i) => (
                <div className="v4m-slider" key={def.key}>
                  <div className="v4m-slider-top">
                    <span className="v4m-slider-label">{def.label}</span>
                    <span className="v4m-slider-val">{labelFor(i, sliders[i])}</span>
                  </div>
                  <div className="v4m-slider-shell">
                    <div className="v4m-slider-track">
                      <div className="v4m-slider-fill" style={{ width: `${sliders[i]}%` }}></div>
                      <div className="v4m-slider-knob" style={{ left: `${sliders[i]}%` }}></div>
                    </div>
                    <input
                      type="range" className="range-overlay"
                      min={0} max={100} value={sliders[i]}
                      onChange={e => {
                        const v = parseInt(e.target.value, 10);
                        setSliders(prev => {
                          if (!prev) return prev;
                          const next = [...prev];
                          next[i] = v;
                          return next;
                        });
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <button className={`v4m-cta${busy ? ' busy' : ''}`} onClick={retune} disabled={busy}>
              <span>{busy ? 'Re-optimizing…' : 'Re-optimize on Quip Network'}</span>
              <span className="v4m-cta-arrow">→</span>
            </button>

            </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
