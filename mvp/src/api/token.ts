// Per-agent capability token store. The token authorizes owner-scoped calls; it
// arrives from the create response (kiosk session) or the QR link fragment (#t=,
// the phone). Kept out of the mock/real seam so both the API client (real.ts) and
// the phone route can reach it. sessionStorage (per-tab) with an in-memory fallback
// for locked-down kiosk browsers where storage may throw.

const PREFIX = 'quip:token:';
const memory = new Map<string, string>();

export function storeAgentToken(agentId: string, token: string): void {
  memory.set(agentId, token);
  try {
    sessionStorage.setItem(PREFIX + agentId, token);
  } catch {
    // Storage blocked — the in-memory copy carries this tab/session.
  }
}

export function getAgentToken(agentId: string): string | null {
  const inMemory = memory.get(agentId);
  if (inMemory) return inMemory;
  try {
    return sessionStorage.getItem(PREFIX + agentId);
  } catch {
    return null;
  }
}
