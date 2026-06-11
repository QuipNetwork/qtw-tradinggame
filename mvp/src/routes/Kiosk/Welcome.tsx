import { useEffect, useRef, useState } from 'react';
import { useSearchParams, Navigate } from 'react-router-dom';
import type { AgentConfig, RoutingResult } from '../../api';
import { getAgent, requestOptimization, assetIconSrc, assetColor, ASSET_BY_TICKER } from '../../api';
import type { PortfolioEntry } from '../../api';
import { renderGlyph, renderFakeQR, strHash, pickStyle } from '../../utils/glyph';
import { labelFor, glyphParams } from '../../utils/strategy';
import KioskStage from './Stage';

const BANKROLL = 10000;

export default function KioskWelcome() {
  const [params] = useSearchParams();
  const agentId = params.get('agent');
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [result, setResult] = useState<RoutingResult | null>(null);
  const glyphRef = useRef<HTMLCanvasElement>(null);
  const qrRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!agentId) return;
    (async () => {
      const a = await getAgent(agentId);
      setAgent(a);

      const cachedRaw = sessionStorage.getItem('quip:lastResult:' + agentId);
      if (cachedRaw) {
        try { setResult(JSON.parse(cachedRaw)); return; } catch { /* fall through */ }
      }
      const r = await requestOptimization(agentId);
      setResult(r);
    })();
  }, [agentId]);

  useEffect(() => {
    if (!agent || !glyphRef.current) return;
    const seed = strHash(agent.name);
    const style = pickStyle(seed);
    renderGlyph(glyphRef.current, Object.assign({
      seed,
      ...glyphParams(agent.sliders),
      cell: 6,
    }, style));
  }, [agent]);

  useEffect(() => {
    if (!agent || !qrRef.current) return;
    renderFakeQR(qrRef.current, 'qtw.quip.network/p/' + agent.name + (agent.handle ?? ''));
  }, [agent]);

  if (!agentId) return <Navigate to="/kiosk" replace />;
  if (!agent) return null;

  const portfolio = result?.portfolio ?? [];
  // Holdings stay weight-sorted, but split into crypto / stocks so each class
  // reads as its own group (the combined allocation bar above keeps the whole).
  const cryptoHoldings = portfolio.filter(e => ASSET_BY_TICKER[e.ticker].class === 'crypto');
  const stockHoldings = portfolio.filter(e => ASSET_BY_TICKER[e.ticker].class === 'stock');
  const dense = portfolio.length > 12;
  const allocRow = (entry: PortfolioEntry) => (
    <div className="v4m-alloc-row" key={entry.ticker}>
      <img className="v4m-alloc-icon" src={assetIconSrc(entry.ticker)} alt="" />
      <span className="v4m-alloc-name">{entry.ticker}</span>
      <span className="v4m-alloc-pct">{entry.pct.toFixed(1)}%</span>
      <span className="v4m-alloc-usd">${entry.usd.toLocaleString()}</span>
    </div>
  );
  const providerWords = (result?.provider ?? 'D-Wave Advantage').split(' ');

  const isQpu = result?.providerType === 'QPU';
  const solveTime = result?.solveTime ?? 0.42;
  const classicalTime = result ? Math.max(solveTime * result.vsClassical, solveTime + 0.1) : 5.88;
  const qBarPct = isQpu ? Math.max(4, (solveTime / classicalTime) * 100) : 100;
  const cBarPct = isQpu ? 100 : Math.max(4, (classicalTime / solveTime) * 100);

  return (
    <KioskStage>
    <div className="qs-v4-mock kiosk-welcome-v4 app-fit">

      <div className="v4m-nav">
        <div className="v4m-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="v4m-nav-divider"></div>
          <span className="v4m-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <span className="v4m-pill">Live · Sign-up</span>
      </div>

      <div className="v4m-hero">
        <h1>Welcome to <span className="it">the competition.</span></h1>
      </div>

      <div className="v4m-body">

        <section className="v4m-main">
          <div style={{ marginBottom: 4 }}>
            <span className="v4m-section-eyebrow cyan-dot cyan">Routed via Quip Network · Solved Just Now</span>
          </div>

          <span className="v4m-route-tag">{result?.providerType ?? 'QPU'}</span>
          <div className="v4m-main-hero">
            {/* Last word of the provider name gets the italic accent:
                "D-Wave Advantage" → D-Wave <it>Advantage.</it>; "Atlas-9" → <it>Atlas-9.</it> */}
            {providerWords.length > 1 && providerWords.slice(0, -1).join(' ') + ' '}
            <span className="it accent">{providerWords[providerWords.length - 1]}.</span>
          </div>
          <div className="v4m-panel-meta" style={{ marginTop: 6 }}></div>

          <div className="v4m-stat-row">
            <div>
              <div className="v4m-stat-big" style={{ color: '#0891B2' }}>{solveTime.toFixed(2)}s</div>
              <span className="v4m-stat-lbl">Solve Time</span>
            </div>
            <div>
              <div className="v4m-stat-mid">{result?.vsClassical ?? 14}×</div>
              <span className="v4m-stat-lbl">Vs Classical</span>
            </div>
          </div>

          <div className="v4m-race">
            <div className="v4m-race-row">
              <span className="v4m-race-label q">{(result?.provider ?? 'D-Wave').split(' ')[0]} · {result?.providerType ?? 'QPU'}</span>
              <div className="v4m-race-bar"><div className="v4m-race-fill q" style={{ width: `${qBarPct}%` }}></div></div>
              <span className="v4m-race-time">{(isQpu ? solveTime : classicalTime).toFixed(2)}s</span>
            </div>
            <div className="v4m-race-row">
              <span className="v4m-race-label">Classical baseline</span>
              <div className="v4m-race-bar"><div className="v4m-race-fill" style={{ width: `${cBarPct}%` }}></div></div>
              <span className="v4m-race-time">{(isQpu ? classicalTime : solveTime).toFixed(2)}s</span>
            </div>
          </div>
        </section>

        <aside className="v4m-mega v4m-agent-panel">

          <div className="v4m-agent-header">
            <canvas ref={glyphRef} className="v4m-agent-glyph" width={220} height={220} aria-label="Your generated agent glyph"></canvas>
            <div className="v4m-agent-ident">
              <div className="v4m-agent-name">{agent.name}.</div>
            </div>
            <div className="v4m-agent-bankroll">
              <div className="v4m-agent-bankroll-lbl">Bankroll</div>
              <div className="v4m-agent-bankroll-num">${BANKROLL.toLocaleString()}</div>
            </div>
          </div>

          {/* Strategy recap — compact horizontal strip (3 sliders) */}
          <div className="v4m-strat-strip">
            <div className="v4m-strat-cell"><span className="v4m-strat-strip-label">Rebalance frequency</span><span className="v4m-strat-val">{labelFor(0, agent.sliders.rebalanceFrequency)}</span></div>
            <div className="v4m-strat-cell"><span className="v4m-strat-strip-label">Risk preference</span><span className="v4m-strat-val">{labelFor(1, agent.sliders.riskPreference)}</span></div>
            <div className="v4m-strat-cell"><span className="v4m-strat-strip-label">Max position size</span><span className="v4m-strat-val">{labelFor(2, agent.sliders.maxPositionSize)}</span></div>
          </div>

          {/* Portfolio — full width; holdings flow into two columns */}
          <div className="v4m-portfolio-block">
            <span className="v4m-section-eyebrow">Your portfolio · {portfolio.length} holding{portfolio.length === 1 ? '' : 's'}</span>
            <div className="v4m-alloc-stack" style={{ marginTop: 10 }}>
              {portfolio.map(entry => (
                <span key={entry.ticker} style={{ width: `${entry.pct}%`, background: assetColor(entry.ticker) }}></span>
              ))}
            </div>
            {/* Grouped by class, weight-sorted within each. >12 holdings switches
                to the dense three-column grid so even a full 25-asset basket fits. */}
            {cryptoHoldings.length > 0 && (
              <>
                <div className="v4m-alloc-subhead">Crypto · {cryptoHoldings.length}</div>
                <div className={`v4m-alloc-grid${dense ? ' dense' : ''}`}>
                  {cryptoHoldings.map(allocRow)}
                </div>
              </>
            )}
            {stockHoldings.length > 0 && (
              <>
                <div className="v4m-alloc-subhead">Stocks · {stockHoldings.length}</div>
                <div className={`v4m-alloc-grid${dense ? ' dense' : ''}`}>
                  {stockHoldings.map(allocRow)}
                </div>
              </>
            )}
          </div>

          <div className="v4m-agent-qr-row">
            <canvas ref={qrRef} className="v4m-agent-qr" width={160} height={160}></canvas>
            <div className="v4m-agent-qr-text">
              <div className="v4m-agent-qr-cap">Scan to open your profile.</div>
              <div className="v4m-agent-qr-sub">Live P&amp;L · Retune anytime</div>
            </div>
          </div>

        </aside>

      </div>
    </div>
    </KioskStage>
  );
}
