# Quip Network · QTW 2026 Trading Competition · MVP

Vite + React + TypeScript app for the Quantum.Tech World 2026 booth experience.

## Run

```bash
npm install
npm run dev
```

Dev server: `http://localhost:5173`

## Routes

| Path | Surface | Form factor |
|---|---|---|
| `/kiosk` | Sign-up form | Kiosk laptop |
| `/kiosk/welcome?agent=<id>` | Post-routing confirmation + QR | Kiosk laptop |
| `/p/:agentId` | Personal profile + retune | Phone (linked via QR) |
| `/tv` | Booth TV rotation (A→B→C, D interrupts) | 1920×1080 booth display |
| `/tv?state=A\|B\|C\|D` | Force a single TV state — useful for design review | Booth display |
| `/tv?agent=<id>` | Force spotlight rotation to a specific leaderboard agent | Booth display |

The development index page at `/` stores the latest created agent id in
`localStorage` after sign-up and uses it for the welcome/profile preview links.
If no local agent has been created yet, those links send you to `/kiosk` first.

## Design source of truth

Mock screens live in `../design-doc.html`. Both this app and that file consume the same shared CSS at `../shared-design/v4-mocks.css` (via a `public/shared-design` symlink). When you edit a mock in `design-doc.html`, the change propagates to this MVP automatically — they cannot drift visually.

Same goes for the SVG symbol library (`../shared-design/symbols.svg.html`): injected at app startup by `src/main.tsx` so `<use href="#crypto-btc" />` etc. work everywhere.

The canvas glyph algorithm lives in `../shared-design/glyph.js` and is imported via the `@shared` Vite alias (`src/utils/glyph.ts` is a thin TypeScript wrapper). Profile QR codes are rendered by `src/utils/qr.ts`.

## API contract

All backend interactions go through `src/api/`:

- `src/api/types.ts` — TypeScript contracts (`AgentConfig`, `RoutingResult`, `LeaderboardEntry`, etc.)
- `src/api/mocks.ts` — offline/demo implementation (random routing, seeded leaderboard, localStorage persistence)
- `src/api/real.ts` — fetch/WebSocket implementation for the backend
- `src/api/index.ts` — single re-export point; uses `real.ts` when `VITE_API_BASE` is set, mocks otherwise

The UI never imports from `mocks.ts` or `real.ts` directly — only via `./index`.
TV routes also use `getLeaderboard`, `getRoutingStats`, and
`getValuationHistory` so the leaderboard, QPU-vs-CPU winner share, provider
breakdown, and spotlight chart come from backend state when connected.

## Deploy

`netlify.toml` configured. Set the build base to `mvp/` and `dist/` as publish dir.
