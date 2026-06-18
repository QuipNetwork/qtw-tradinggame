import { useEffect, useRef, useState } from 'react';
import { useSearchParams, Navigate } from 'react-router-dom';
import type { AgentConfig, AgentUpdate, RoutingResult } from '../../api';
import { getAgent, requestOptimization, subscribeAgent, assetIconSrc, assetColor, ASSET_BY_TICKER } from '../../api';
import type { PortfolioEntry } from '../../api';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';
import { renderQR } from '../../utils/qr';
import { solverRaceComparison, solverRaceRows } from '../../utils/solverRace';
import { labelFor, glyphParams } from '../../utils/strategy';
import KioskStage from './Stage';

const BANKROLL = 10000;
const WHOLE_USD = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

export default function KioskWelcome() {
  const [params] = useSearchParams();
  const agentId = params.get('agent');
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [result, setResult] = useState<RoutingResult | null>(null);
  const [live, setLive] = useState<AgentUpdate | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const glyphRef = useRef<HTMLCanvasElement>(null);
  const qrRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
      if (!agentId) return;
    (async () => {
      const a = await getAgent(agentId);
      setAgent(a);
      setQrUrl(sessionStorage.getItem('quip:qrUrl:' + agentId));

      const cachedRaw = sessionStorage.getItem('quip:lastResult:' + agentId);
      if (cachedRaw) {
        try { setResult(JSON.parse(cachedRaw)); return; } catch { /* fall through */ }
      }
      const r = await requestOptimization(agentId);
      setResult(r);
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
      cell: 6,
    }, style));
  }, [agent]);

  useEffect(() => {
    if (!agentId || !qrRef.current) return;
    const value = qrUrl ?? `${window.location.origin}/p/${agentId}`;
    renderQR(qrRef.current, value).catch(() => {});
  }, [agentId, qrUrl]);

  if (!agentId) return <Navigate to="/kiosk" replace />;
  if (!agent) return null;

  const portfolio: PortfolioEntry[] = live?.holdings?.length
    ? live.holdings.map(h => ({ ticker: h.ticker, pct: h.pct, usd: h.usd }))
    : result?.portfolio ?? [];
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
      <span className="v4m-alloc-usd">${WHOLE_USD.format(entry.usd)}</span>
    </div>
  );
  const providerWords = (result?.provider ?? 'D-Wave Advantage').split(' ');

  const solveTime = result?.solveTime ?? 0.42;
  const raceRows = solverRaceRows(result);
  const raceComparison = solverRaceComparison(result);

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
              <div className="v4m-stat-mid">{raceComparison.value}</div>
              <span className="v4m-stat-lbl">{raceComparison.label}</span>
            </div>
          </div>

          <div className="v4m-race">
            {raceRows.map(row => (
              <div className={`v4m-race-row${row.isWinner ? ' winner' : ''}${row.feasible ? '' : ' muted'}`} key={`${row.provider}-${row.status}`}>
                <span className={`v4m-race-label${row.isWinner ? ' q' : ''}`}>
                  {row.label}
                  <span className="v4m-race-detail">{row.detail}</span>
                </span>
                <div className="v4m-race-bar"><div className={`v4m-race-fill${row.isWinner ? ' q' : ''}`} style={{ width: `${row.barPct}%` }}></div></div>
                <span className="v4m-race-time">{row.timeLabel}</span>
              </div>
            ))}
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
              <div className="v4m-agent-bankroll-num">${WHOLE_USD.format(BANKROLL)}</div>
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
            <span className="v4m-section-eyebrow">Your portfolio · {portfolio.length} holding{portfolio.length === 1 ? '' : 's'} · {live?.stale ? 'Last close' : 'Live'}</span>
            <div className="v4m-alloc-stack" style={{ marginTop: 10 }}>
              {portfolio.map(entry => (
                <span key={entry.ticker} style={{ width: `${entry.pct}%`, background: assetColor(entry.ticker) }}></span>
              ))}
            </div>
            <div className="v4m-holdings-scroll">
              {/* Grouped by class, weight-sorted within each. >12 holdings switches
                  to the dense three-column grid so even a full 28-asset basket fits. */}
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
