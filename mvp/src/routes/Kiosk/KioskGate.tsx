import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { IS_MOCK } from '../../api';
import { kioskKey } from '../../api/kiosk';

// Opt-in via VITE_KIOSK_GATE (set in the booth build). With it on and a real backend:
//   • the booth tablet (opened via the secret ?k=… link → kioskKey present) creates UNLIMITED agents;
//   • a public visitor may create exactly ONE agent per browser — if they already have one we resume
//     it instead of showing the form again (the backend also dedups one-agent-per-email).
// The backend no longer BLOCKS keyless sign-ups, so public creation works; the key only lifts limits.
// Mock/demo builds are never gated, so local previews keep working.
const GATE_ON = Boolean(import.meta.env.VITE_KIOSK_GATE);

function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

// A public visitor who already created their one agent → send them to it. The tokenised resume URL
// (/p/{id}#t={token}) keeps them authorised across sessions; fall back to the bare profile route.
function ResumeExisting({ url }: { url: string }) {
  useEffect(() => {
    try {
      window.location.assign(url);
    } catch {
      /* navigation blocked (locked-down browser) — the link below still works */
    }
  }, [url]);
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
        background: '#0b0b0c',
        color: '#f2f2f2',
        fontFamily: "'ABC Gaisyr', Georgia, serif",
      }}
    >
      <h1 style={{ margin: 0, fontSize: 28 }}>Resuming your agent…</h1>
      <p style={{ margin: 0, maxWidth: 420, color: '#a9a9a9', fontFamily: 'system-ui, sans-serif' }}>
        You’ve already created an agent on this device.{' '}
        <a href={url} style={{ color: '#22d3ee' }}>Open it</a> if you’re not redirected.
      </p>
    </main>
  );
}

export default function KioskGate({ children }: { children: ReactNode }) {
  // Public (no secret key) on a gated booth build → one agent per browser: already created one →
  // resume it; otherwise fall through to the sign-up. The booth tablet (kioskKey) is never limited.
  if (GATE_ON && !IS_MOCK && !kioskKey()) {
    const resume = readLocal('quip:resumeUrl');
    const lastAgentId = readLocal('quip:lastAgentId');
    if (resume || lastAgentId) {
      return <ResumeExisting url={resume || `/p/${lastAgentId}`} />;
    }
  }
  return <>{children}</>;
}
