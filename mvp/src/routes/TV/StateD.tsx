import { useEffect, useRef, useState } from 'react';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';

function nowClock(): string {
  return new Date().toLocaleTimeString('en-GB', { hour12: false });
}

export default function StateD({ name = 'Lattice Theory' }: { name?: string }) {
  const glyphRef = useRef<HTMLCanvasElement>(null);
  const [clock, setClock] = useState(nowClock);

  useEffect(() => {
    const id = window.setInterval(() => setClock(nowClock()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!glyphRef.current) return;
    const seed = strHash(name);
    const style = pickStyle(seed);
    renderGlyph(glyphRef.current, Object.assign({
      seed, p1: 0.7, p2: 0.78, p3: 0.5, p4: 0.3, p5: 0.55, cell: 8,
    }, style));
  }, [name]);

  return (
    <div className="bigscreen dir-quipsite v4 state-a">
      <div className="qs-nav">
        <div className="qs-mark">
          <svg className="quip-wm"><use href="#quip-wm" /></svg>
          <div className="nav-divider"></div>
          <span className="nav-eyebrow">Quantum.Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">New agent · {clock}</span><span className="bar"></span></div>
      </div>

      <div className="qs-body-v4">
        <div className="qs-hero-left">
          <div className="left">
            <h1>New agent <span className="it">on the board.</span></h1>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>New agent</div>
            <div className="countdown" style={{ fontFamily: 'Georgia,serif', fontStyle: 'italic', fontSize: '3.4cqh', color: '#18181b', fontVariantNumeric: 'tabular-nums' }}>Just signed up</div>
          </div>
        </div>

        <div className="qs-table-area">
          <div className="welcome-stage">
            <canvas ref={glyphRef} className="welcome-glyph" width={260} height={260} aria-hidden="true"></canvas>
            <div className="welcome-name">{name}</div>
            <div className="welcome-caption">Portfolio optimized by <span className="it">Quip Network.</span></div>
          </div>
        </div>

        <aside className="qs-rail v4-rail state-a-rail">
          <div className="v4-mega">
            <div className="v4-section" style={{ padding: '2cqh 1.8cqw' }}>
              <div className="v3-panel-head" style={{ border: 'none', padding: 0, gap: '0.6cqh' }}>
                <span className="v3-panel-eyebrow" style={{ fontSize: '1.6cqh' }}>Now routing</span>
                <span className="v3-panel-hero" style={{ fontSize: '3.4cqh', lineHeight: 1.05 }}>On Quip <span className="accent">Network.</span></span>
              </div>
              <div className="v3-panel-body" style={{ padding: '1.6cqh 0 0 0' }}>
                <div className="v4-pr q" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '1cqh' }}>
                  <span className="type" style={{ fontSize: '1.5cqh', padding: '0.5cqh 1cqw', letterSpacing: '0.14em' }}>RACE</span>
                  <span style={{ fontFamily: "Georgia, 'Times New Roman', serif", fontStyle: 'italic', fontSize: '3.2cqh', lineHeight: 1.05, color: '#18181b', wordBreak: 'break-word' }}>
                    SA vs <span style={{ color: '#0891B2' }}>D-Wave.</span>
                  </span>
                </div>
              </div>
              <div style={{
                borderTop: '1px solid #ececef', paddingTop: '1.4cqh', marginTop: '1.6cqh',
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: '1.5cqh', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase',
                color: '#71717b', lineHeight: 1.5,
              }}>
                Fastest valid optimum wins
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
