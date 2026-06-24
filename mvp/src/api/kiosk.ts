// Booth-kiosk unlock key. Captured once from the ?k=<key> the booth tablet is
// opened with, persisted locally, and sent as X-Kiosk-Key on signup so the backend
// can keep agent creation off the public web. Reading is synchronous so the gate
// decision is available on the first render.
const STORAGE_KEY = 'qtw_kiosk_key';

export function kioskKey(): string | null {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('k');
    if (fromUrl) {
      try {
        localStorage.setItem(STORAGE_KEY, fromUrl);
      } catch {
        // Locked-down kiosk browsers may block storage; the URL value still works this load.
      }
      return fromUrl;
    }
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
