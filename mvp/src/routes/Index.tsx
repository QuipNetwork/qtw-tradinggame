import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { renderGlyph, strHash, pickStyle } from '../utils/glyph';

// The production landing surface, in the design-doc theme (masthead + serif
// hero + meta strip). It routes cleanly into every booth surface: the kiosk,
// the phone profile of the agent created this session, and the TV in all its
// states (auto-rotate plus each forced state, including the new-agent interrupt).

type SurfaceLink = { label: string; to: string; note?: string; external?: boolean };
type Surface = { num: string; id: string; title: string; formFactor: string; blurb: string; links: SurfaceLink[] };

function latestCreatedAgentId(): string | null {
  try {
    return localStorage.getItem('quip:lastAgentId');
  } catch {
    return null;
  }
}

function buildSurfaces(latestAgentId: string | null): Surface[] {
  const welcome: SurfaceLink = latestAgentId
    ? { label: 'Welcome · latest created agent', to: `/kiosk/welcome?agent=${latestAgentId}`, note: 'Completion screen for the agent created this session.' }
    : { label: 'Welcome · create an agent first', to: '/kiosk', note: 'Create an agent to enable the latest-agent welcome link.' };
  const profile: SurfaceLink = latestAgentId
    ? { label: 'Phone profile · latest created agent', to: `/p/${latestAgentId}`, note: 'The profile shown when an agent is created — P&L, retune, edit basket.' }
    : { label: 'Phone profile · create an agent first', to: '/kiosk', note: 'Create an agent to open its /p/{agent_id} profile.' };

  return [
    {
      num: '01', id: 'kiosk', title: 'Booth kiosk', formFactor: 'Laptop / iPad · landscape',
      blurb: 'The booth screen attendees walk up to. Name an agent, pick a watchlist, tune three sliders, launch.',
      links: [{ label: 'Sign-up', to: '/kiosk', note: 'Entry point — fills sliders and submits.' }, welcome],
    },
    {
      num: '02', id: 'phone', title: 'Phone profile', formFactor: 'Phone · portrait',
      blurb: 'The personal profile each player gets via QR — live P&L that moves with the market, retune mid-conference.',
      links: [profile],
    },
    {
      num: '03', id: 'tv', title: 'Booth TV', formFactor: '1920×1080 · landscape',
      blurb: 'The big-screen rotator behind the booth: leaderboard, top-10 spotlight, a how-it-works welcome, and a new-agent interrupt.',
      links: [
        { label: 'Auto-rotate · A → B → C (D interrupts)', to: '/tv', note: 'Default rotation: leaderboard → spotlight → welcome; a new agent interrupts.' },
        { label: 'Force state A · Leaderboard', to: '/tv?state=A' },
        { label: 'Force state B · Top-10 spotlight', to: '/tv?state=B' },
        { label: 'Force state C · Welcome / how it works', to: '/tv?state=C' },
        { label: 'Force state D · New-agent interrupt', to: '/tv?state=D' },
      ],
    },
    {
      num: '04', id: 'doc', title: 'Design doc', formFactor: 'Reference',
      blurb: 'End-to-end project summary: attendee flow, screen mockups, big-screen rotation, slider→QUBO mapping, architecture.',
      links: [{ label: 'Open the design doc', to: '/design-doc.html', external: true, note: 'Full project summary in one page.' }],
    },
  ];
}

export default function Index() {
  const surfaces = buildSurfaces(latestCreatedAgentId());
  const glyphRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!glyphRef.current) return;
    const seed = strHash('Quip Network · QTW 2026 Trading Competition');
    // 'mixed' palette (coral + yellow + cyan + purple) matches the design-doc
    // hero — more alive than the seed's monochrome coral, all brand colors.
    renderGlyph(glyphRef.current, Object.assign({ seed, cell: 5 }, pickStyle(seed), { palette: 'mixed' }));
  }, []);

  const renderLink = (link: SurfaceLink) => {
    const inner = (
      <>
        <span className="surf-link-label">{link.label}</span>
        <span className="surf-link-to">{link.to}</span>
        {link.note && <span className="surf-link-note">{link.note}</span>}
      </>
    );
    return link.external ? (
      <a key={link.to + link.label} className="surf-link" href={link.to}>{inner}</a>
    ) : (
      <Link key={link.to + link.label} className="surf-link" to={link.to}>{inner}</Link>
    );
  };

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <nav className="doc-nav" aria-label="Surfaces">
        <div className="doc-nav-inner">
          <a href="#top" className="doc-nav-brand"><span className="grad">QTW Trading Competition</span></a>
          <ul className="doc-nav-list">
            {surfaces.map(s => (
              <li key={s.id}><a href={`#${s.id}`}><span className="num">{s.num}</span>{s.title}</a></li>
            ))}
          </ul>
        </div>
      </nav>

      <div className="page landing-enter" id="top">
        <header className="hero">
          <div className="kicker">Quantum.Tech World 2026 · Trading Competition</div>
          <div className="hero-title-row">
            <h1>The Quip Network<br /><span className="grad">Trading Competition</span></h1>
            <canvas ref={glyphRef} width={160} height={160} aria-label="Quip generative glyph"></canvas>
          </div>
          <p className="lede">
            A booth activation where attendees name an agent, pick a watchlist from the 28-asset
            universe, and tune three strategy sliders. Quip Network routes every re-optimization
            across quantum and classical solvers; a leaderboard tracks P&amp;L across the conference.
          </p>

          <div className="hero-facts">
            <div><span>Format</span><strong>Booth kiosk + phone profile</strong></div>
            <div><span>Dates</span><strong>Jun 25–26, 2026 · continuous</strong></div>
            <div><span>Prize tier</span><strong>Top 10 win</strong></div>
          </div>
        </header>

        <main id="main">
        {surfaces.map(s => (
          <section id={s.id} key={s.id}>
            <div className="kicker">{s.num} · {s.title}</div>
            <div className="surf-head">
              <h2>{s.title}</h2>
              <span className="surf-form">{s.formFactor}</span>
            </div>
            <p className="surf-blurb">{s.blurb}</p>
            <div className="surf-links">{s.links.map(renderLink)}</div>
          </section>
        ))}
        </main>

        <footer className="surf-foot">
          <span>Source · <a href="https://gitlab.com/quip.network/qtw-tradinggame">gitlab.com/quip.network/qtw-tradinggame</a></span>
          <span>Mock data only — no real trading.</span>
        </footer>
      </div>
    </>
  );
}
