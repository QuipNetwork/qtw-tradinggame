# Overnight frontend-polish backlog

- **Branch:** `overnight-frontend-2026-06-22` (base commit `dd540b3` = hardening + TV, pending review)
- **Mode:** self-paced `/loop`, one item per wake, implement-on-branch, never merge.
- **Reviewed by the user in the morning.**

## Guardrails (re-read every wake — do not violate)
1. **Branch only.** Commit to `overnight-frontend-2026-06-22`. Never checkout/commit `main` or `deployment-dev`. Never merge.
2. **Frontend only.** Edit only under `mvp/` and `shared-design/` (+ this backlog). NEVER edit `backend/`. Anything needing a backend/DB change → write it under "Propose only", don't implement.
3. **Keep the identity.** The landing uses the design-doc theme and the user likes it — refine, don't redesign. Keep the v4 system (Quip mark, mono eyebrows, cyan `--signal`, coral, Georgia serif). Respect `prefers-reduced-motion` (global block already neutralizes animations).
4. **Verify before commit:** `cd mvp && npx tsc -b && npm run -s lint && npm run -s build` must all pass. If a change breaks them, fix or revert — never commit broken code.
5. **Small + atomic.** One backlog item per commit so morning diffs are reviewable. Concise commit messages, NO Claude co-author trailer.
6. **Don't touch** the user's flagged-for-their-eye items (see Propose only).

## IMPLEMENT — ordered by impact (do the top undone one each wake)

### Real / production feel
- [x] **R1 · Loading skeletons.** Done `672f9c5` — StatusScreen busy state now renders a subtle 3-bar shimmer (currentColor, ≤0.14 opacity; reduced-motion → static). Follow-up: per-surface skeleton shapes if desired.
- [ ] **R2 · Motion language consistency.** Audit entrance transitions across surfaces; unify on the existing fade-up/fade-in vocabulary; ensure every animation is reduced-motion-safe. No new libraries.
- [ ] **R3 · Number-formatting consistency.** Route every $/% through the shared `utils/format.ts`; consistent rounding/tabular-nums on P&L, totals, allocation. Add `format` helpers if needed.
- [ ] **R4 · SignUp double-submit guard.** If `submitAgent` succeeds but `requestOptimization` throws, don't strand the user or allow a duplicate agent on re-press; navigate to welcome (it re-solves) or disable re-submit.

### Phone
- [ ] **P1 · Live holdings on the phone profile.** The phone shows P&L but not the moving portfolio. Add a compact, live per-holding strip (the mock already streams `holdings`) — reuse the allocation bar + value-flash so the player watches their own prices move. Design-careful; keep the screen from overflowing (it scrolls).
- [ ] **P2 · Phone heading + landmark.** Add an `<h1>` (agent name) and `<main>` so the profile has real document structure.

### TV
- [ ] **T1 · StateC live asset changes.** Replace the deterministic `fakeChange` with a gently drifting per-asset 24h change (module state, vol-scaled) so the explainer's asset list feels alive. Frontend-only.
- [ ] **T2 · Spotlight derived labels.** Replace StateB's hardcoded "02h 14m on the board" / "4s ago" with values derived from data (a ticking relative clock; omit if no timestamp available) rather than frozen strings.
- [ ] **T3 · TV landmarks + transition polish.** `<main>` on the TV; confirm the cross-fade reads well; ensure the rotation timer can't double-fire on a refresh (stale-closure check in BoothTV).

### Accessibility / production
- [ ] **A1 · Landmarks + headings everywhere.** `<main>` on kiosk/phone/TV; promote section eyebrows to real headings (or visually-hidden ones) for screen-reader structure.
- [ ] **A2 · Reach-out "No thanks" semantics.** It's mutually exclusive — give it radio semantics (or a separate control) so SR users understand selecting it clears the rest.
- [ ] **A3 · RR v7 future flags.** Opt into `v7_startTransition` + `v7_relativeSplatPath` on BrowserRouter to clear the console advisories; verify lazy/Suspense still work.
- [ ] **A4 · Tap targets (phone side only).** Raise phone-side hit areas (basket-back, slider knob) toward 44px WITHOUT touching the fixed 1024×768 kiosk layout. Per-surface; verify the kiosk doesn't regress.

### Polish / hygiene
- [ ] **H1 · Welcome QR.** Investigate the blank QR canvas for seeded agents (now that qrcode is lazy); ensure it renders.
- [ ] **H2 · Landing rhythm.** Minor vertical-rhythm/spacing refinements on the hub; vary the hero glyph palette if it reads too monochrome. Keep the theme.

## PROPOSE ONLY — do NOT implement (write/refine a proposal in this section)
- **Cyan/coral contrast recolor** (`#0891B2` CTA, coral text fail AA). Needs the user's eye — it shifts the brand identity. Draft exact token changes + before/after ratios; don't apply.
- **Basket persistence** — `saveBasket` is local-only on the real backend (no `PATCH /agents`). Needs a backend endpoint or a product decision (fold into retune). Backend = out of scope.
- **DB / real-data feel** — valuation-history granularity, snapshot cadence, persistence guarantees. Backend/DB = propose only.
- **`v4-mocks.css` hashing/purge** — 226 KB shared with design-doc.html; risk of breaking `url()`/the doc. Draft a safe plan (Vite import + per-route purge) rather than applying blind.

## Progress log (loop appends here)
- 2026-06-22 · R1 loading skeletons → `672f9c5` (tsc/lint/build green).
