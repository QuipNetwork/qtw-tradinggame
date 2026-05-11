import { Link } from 'react-router-dom';

type Surface = {
  title: string;
  blurb: string;
  formFactor: string;
  links: { label: string; to: string; note?: string }[];
};

const SURFACES: Surface[] = [
  {
    title: 'Kiosk',
    blurb: 'The booth laptop attendees walk up to. Name an agent, tune five sliders, launch.',
    formFactor: 'Laptop · landscape',
    links: [
      { label: 'Sign-up', to: '/kiosk', note: 'Entry point — fills sliders and submits' },
      { label: 'Welcome (post-launch)', to: '/kiosk/welcome?agent=a06', note: 'Confirmation + QR (using demo agent a06)' },
    ],
  },
  {
    title: 'Phone',
    blurb: 'Personal profile each player gets via QR. Live P&L, retune sliders mid-conference.',
    formFactor: 'Phone · portrait',
    links: [
      { label: 'Profile · Lattice Theory', to: '/p/a06', note: 'Demo agent — drag the sliders to trigger a re-route' },
      { label: 'Profile · Hilbert Spaceship', to: '/p/a01', note: 'Top of leaderboard' },
    ],
  },
  {
    title: 'Booth TV',
    blurb: 'Big-screen rotator behind the booth. Welcome splash, leaderboard, top-10 spotlight.',
    formFactor: '1920×1080 · landscape',
    links: [
      { label: 'Auto-rotate (A→B→C, D interrupts)', to: '/tv', note: 'Default cinematic rotation' },
      { label: 'Force state A · Welcome splash', to: '/tv?state=A' },
      { label: 'Force state B · Leaderboard', to: '/tv?state=B' },
      { label: 'Force state C · Top-10 spotlight', to: '/tv?state=C' },
      { label: 'Force state D · New-agent interrupt', to: '/tv?state=D' },
    ],
  },
];

const linkStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
  padding: '10px 12px',
  borderRadius: 8,
  border: '1px solid #e4e4e7',
  textDecoration: 'none',
  color: '#18181b',
  background: 'white',
  transition: 'border-color 120ms, background 120ms',
};

const cardStyle: React.CSSProperties = {
  background: 'white',
  border: '1px solid #e4e4e7',
  borderRadius: 12,
  padding: 24,
  display: 'flex',
  flexDirection: 'column',
  gap: 14,
};

const kickerStyle: React.CSSProperties = {
  fontFamily: 'JetBrains Mono, ui-monospace, monospace',
  fontSize: 11,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: '#71717a',
};

export default function Index() {
  return (
    <div style={{ minHeight: '100vh', background: '#fafafa', padding: '48px 24px 80px' }}>
      <div style={{ maxWidth: 980, margin: '0 auto' }}>
        <header style={{ marginBottom: 40 }}>
          <div style={kickerStyle}>Quantum Tech World 2026 · MVP preview · v0.1</div>
          <h1 style={{ fontSize: 36, fontWeight: 700, margin: '8px 0 12px', letterSpacing: '-0.02em' }}>
            Quip Network · QTW 2026 Trading Competition
          </h1>
          <p style={{ fontSize: 17, lineHeight: 1.55, color: '#52525b', maxWidth: 720, margin: 0 }}>
            A booth activation where attendees name an agent, set five strategy sliders, and watch
            their portfolio compete in real time — every retune is routed through the Quip Network.
            This page lists every surface in the MVP so you can preview any of them in isolation.
          </p>
        </header>

        <section style={{ marginBottom: 40 }}>
          <div style={kickerStyle}>Design doc</div>
          <h2 style={{ fontSize: 22, fontWeight: 600, margin: '6px 0 12px' }}>Full project summary</h2>
          <a
            href="/summary.html"
            style={{
              ...cardStyle,
              textDecoration: 'none',
              color: '#18181b',
              display: 'block',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
              <div>
                <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 4 }}>summary.html</div>
                <div style={{ fontSize: 14, color: '#52525b', lineHeight: 1.5 }}>
                  End-to-end design doc: reference activation, attendee flow, all screen mockups, big-screen
                  rotation, scope, slider→QUBO mapping, architecture, glyph playground, and open TBDs.
                </div>
              </div>
              <div style={{ fontSize: 18, color: '#71717a', flexShrink: 0 }}>→</div>
            </div>
          </a>
        </section>

        <section style={{ marginBottom: 40 }}>
          <div style={kickerStyle}>Live MVP · React app</div>
          <h2 style={{ fontSize: 22, fontWeight: 600, margin: '6px 0 16px' }}>Surfaces</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
            {SURFACES.map(surface => (
              <div key={surface.title} style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{surface.title}</h3>
                  <span style={{ fontSize: 12, color: '#71717a', fontFamily: 'JetBrains Mono, ui-monospace, monospace' }}>
                    {surface.formFactor}
                  </span>
                </div>
                <p style={{ fontSize: 14.5, color: '#52525b', margin: 0, lineHeight: 1.55 }}>{surface.blurb}</p>
                <div style={{ display: 'grid', gap: 8 }}>
                  {surface.links.map(link => (
                    <Link key={link.to + link.label} to={link.to} style={linkStyle}>
                      <span style={{ fontSize: 14.5, fontWeight: 500 }}>{link.label}</span>
                      <span style={{ fontSize: 12, color: '#71717a', fontFamily: 'JetBrains Mono, ui-monospace, monospace' }}>
                        {link.to}
                      </span>
                      {link.note && (
                        <span style={{ fontSize: 12.5, color: '#52525b', marginTop: 2 }}>{link.note}</span>
                      )}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <footer style={{ borderTop: '1px solid #e4e4e7', paddingTop: 20, fontSize: 13, color: '#71717a' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <span>Source: <a href="https://gitlab.com/quip.network/qtw-tradinggame" style={{ color: '#52525b' }}>gitlab.com/quip.network/qtw-tradinggame</a></span>
            <span>Mock data only — no real trading.</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
