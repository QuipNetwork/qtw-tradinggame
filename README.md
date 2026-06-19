# Quip Network · QTW 2026 Trading Competition

Booth activation for **Quantum.Tech World 2026** (Jun 25–26, 2026). Attendees create a trading agent at a kiosk, tune three strategy sliders, and watch their portfolio compete in real time — every retune is routed through the Quip Network across quantum and classical providers.

## Start here

| What | Where |
|---|---|
| **Live MVP preview** (every surface, one-click) | https://qtw.quip.network |
| **Design doc** (full project summary) | [`design-doc.html`](./design-doc.html) — open in browser, or visit `/design-doc.html` on the deployed site |
| **MVP source** | [`mvp/`](./mvp) — Vite + React + TypeScript |

The MVP index page at `/` lists every surface (kiosk, phone, booth TV states) with previewable demo links and a link to the design doc — share that URL for any review.

## Repo layout

```
design-doc.html        Full project summary (open in any browser)
mvp/                   Vite + React + TypeScript app — the live MVP
reference-files/       Base @ Consensys Miami screenshots (referenced by design doc)
shared-design/         CSS + canvas glyph algorithms shared between MVP and doc
```

## Run the MVP locally

```bash
cd mvp
npm install
npm run dev          # http://localhost:5173
```

See [`mvp/README.md`](./mvp/README.md) for routes, API contract, and the mock-to-real backend swap.
See [`backend/README.md`](./backend/README.md) for the Python backend (solver race, API, CLI) and [`docs/BACKEND_DAG.md`](./docs/BACKEND_DAG.md) for the system dataflow.

## Deploy

`netlify.toml` is wired up. Every push to `main` triggers an auto-build for the Netlify deployment surfaced at https://qtw.quip.network.

## Engineering handoff

The design doc has the full picture. Key sections for a building team:

- **Section 08 · Architecture** — component overview, data flow, retune loop
- **Section 09 · API contract** — the four functions the back-end implements (`submitAgent`, `getAgent`, `requestOptimization`, `subscribeAgent`) and where they live in code
- **Section 10 · Hardware & venue** — what we'll have onsite
- **Section 12 · Open questions** — TBDs with owning group on each
