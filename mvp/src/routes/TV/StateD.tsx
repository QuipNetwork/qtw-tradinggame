import { useEffect, useRef } from 'react';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';

export default function StateD({ name = 'Lattice Theory' }: { name?: string }) {
  const glyphRef = useRef<HTMLCanvasElement>(null);

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
          <span className="nav-eyebrow">Quantum Tech World 2026 · Trading Competition</span>
        </div>
        <div className="h-eyebrow"><span className="lbl">Welcome · 14:22:08</span><span className="bar"></span></div>
      </div>

      <div className="qs-body-v4">
        <div className="qs-hero-left">
          <div className="left">
            <h1>Welcome to <span className="it">the competition.</span></h1>
          </div>
          <div className="right">
            <div className="lbl" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: '1.3cqh', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#71717b' }}>New agent · Player #247</div>
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
                <span className="v3-panel-eyebrow" style={{ fontSize: '1.6cqh' }}>First solve</span>
                <span className="v3-panel-hero" style={{ fontSize: '3.4cqh', lineHeight: 1.05 }}>Solved <span className="accent">by.</span></span>
              </div>
              <div className="v3-panel-body" style={{ padding: '1.6cqh 0 0 0' }}>
                <div className="v4-pr q" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '1cqh' }}>
                  <span className="type" style={{ fontSize: '1.5cqh', padding: '0.5cqh 1cqw', letterSpacing: '0.14em' }}>QPU</span>
                  <span style={{ fontFamily: "Georgia, 'Times New Roman', serif", fontStyle: 'italic', fontSize: '3.2cqh', lineHeight: 1.05, color: '#18181b', wordBreak: 'break-word' }}>
                    D-Wave <span style={{ color: '#0891B2' }}>Advantage.</span>
                  </span>
                </div>
              </div>
              <div style={{
                borderTop: '1px solid #ececef', paddingTop: '1.4cqh', marginTop: '1.6cqh',
                display: 'flex', flexDirection: 'column', gap: '0.6cqh',
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: '1.6cqh', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1cqw' }}>
                  <span style={{ color: '#71717b' }}>Solve time</span>
                  <span style={{ color: '#0891B2' }}>0.42s</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1cqw' }}>
                  <span style={{ color: '#71717b' }}>Vs classical</span>
                  <span style={{ color: '#18181b' }}>14× faster</span>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
