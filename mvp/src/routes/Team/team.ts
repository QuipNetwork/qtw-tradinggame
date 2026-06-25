// Team-directory unlock key. The internal surfaces directory lives behind a
// light gate: the shareable link is `/team?k=<key>`. The key is captured once
// from `?k=`, persisted locally, and compared against the expected value.
// Reading is synchronous so the gate decision is available on the first render.
//
// This is FRONTEND secrecy only (keeps the internal directory off the public
// landing) — it is not an auth boundary. Production sets VITE_TEAM_KEY on the
// deploy; local dev falls back to a known key so previews keep working.
const STORAGE_KEY = 'qtw_team_key';

const EXPECTED = (import.meta.env.VITE_TEAM_KEY as string | undefined) || 'quip-internal';

function storedOrUrlKey(): string | null {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('k');
    if (fromUrl) {
      try {
        localStorage.setItem(STORAGE_KEY, fromUrl);
      } catch {
        // Some locked-down browsers block storage; the URL value still works this load.
      }
      return fromUrl;
    }
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function teamUnlocked(): boolean {
  return storedOrUrlKey() === EXPECTED;
}
