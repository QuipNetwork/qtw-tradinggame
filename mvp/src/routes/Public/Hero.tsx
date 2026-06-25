import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { renderGlyph, strHash, pickStyle } from '../../utils/glyph';

// Public hero: mono kicker w/ live dot, serif headline, lede, two CTAs, a stat
// strip, and the SAME generative glyph used across the booth (canvas renderGlyph,
// all-brand 'mixed' palette) as the agent's mark.
export default function Hero() {
  const glyphRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!glyphRef.current) return;
    const seed = strHash('Quip Network · QTW 2026 · Race the quantum computer');
    renderGlyph(glyphRef.current, Object.assign({ seed, cell: 6 }, pickStyle(seed), { palette: 'mixed' }));
  }, []);

  return (
    <header className="qpub-hero" data-reveal>
      <div className="qpub-hero-copy">
        <span className="qpub-kicker">Quantum.Tech World 2026</span>
        <h1>Race a portfolio on a <em>real</em> quantum&nbsp;computer.</h1>
        <p className="qpub-lede">
          Build a trading agent, pick your assets, and set three dials. Each rebalance,
          quantum and classical solvers compete to optimize the portfolio.
        </p>
        <div className="qpub-cta-row">
          <Link to="/kiosk" className="qpub-btn qpub-btn-solid">Create your agent <span aria-hidden>→</span></Link>
          <a href="#leaderboard" className="qpub-btn qpub-btn-ghost">See the leaderboard</a>
        </div>
        <dl className="qpub-hero-stats">
          <div><dt>Virtual bankroll</dt><dd>$10K</dd></div>
          <div><dt>Asset universe</dt><dd>28</dd></div>
          <div><dt>Every rebalance</dt><dd>QPU vs CPU</dd></div>
        </dl>
      </div>
      <div className="qpub-hero-glyph">
        <canvas ref={glyphRef} width={176} height={176} aria-label="Quip generative glyph" />
      </div>
    </header>
  );
}
