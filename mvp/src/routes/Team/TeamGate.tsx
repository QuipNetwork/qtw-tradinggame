import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { teamUnlocked } from './team';

// Gate for the internal surfaces directory. Without a matching ?k=<key> the page
// shows a locked screen instead of the directory, so a public visitor who guesses
// /team still can't see the kiosk / TV / design-doc links. Always noindex.
export default function TeamGate({ children }: { children: ReactNode }) {
  useEffect(() => {
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex, nofollow';
    document.head.appendChild(meta);
    return () => {
      document.head.removeChild(meta);
    };
  }, []);

  if (!teamUnlocked()) {
    return (
      <main
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          padding: 40,
          textAlign: 'center',
          background: '#0a0a0b',
          color: '#f2f2f2',
          fontFamily: "'ABC Gaisyr', Georgia, serif",
        }}
      >
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 500 }}>Team only</h1>
        <p style={{ margin: 0, maxWidth: 440, color: '#a9a9a9', fontFamily: "'ABC Favorit', system-ui, sans-serif" }}>
          This is the internal booth directory. Open it from the team link
          (<code>/team?k=…</code>) to reach the kiosk, phone, and TV surfaces.
        </p>
      </main>
    );
  }
  return <>{children}</>;
}
