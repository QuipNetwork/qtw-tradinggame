import type { ReactNode } from 'react';
import { IS_MOCK } from '../../api';
import { kioskKey } from '../../api/kiosk';

// Opt-in via VITE_KIOSK_GATE (set in the booth build). When on with a real backend,
// the kiosk must be unlocked with ?k=<key> from the booth link; a public visitor with
// no key can't open the signup form (the backend also rejects keyless POST /agents).
// Mock/demo builds are never gated, so local previews keep working.
const GATE_ON = Boolean(import.meta.env.VITE_KIOSK_GATE);

export default function KioskGate({ children }: { children: ReactNode }) {
  if (GATE_ON && !IS_MOCK && !kioskKey()) {
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
        <h1 style={{ margin: 0, fontSize: 28 }}>Kiosk locked</h1>
        <p style={{ margin: 0, maxWidth: 420, color: '#a9a9a9', fontFamily: 'system-ui, sans-serif' }}>
          Open this kiosk from the booth link to create an agent. An agent you already
          created is always reachable from the QR link or email you received.
        </p>
      </main>
    );
  }
  return <>{children}</>;
}
