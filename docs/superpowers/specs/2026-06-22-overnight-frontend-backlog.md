# Overnight frontend-polish backlog

- **Branch:** `frontend-polishing` (base commit `dd540b3` = hardening + TV, pending review)
- **Mode:** self-paced `/loop`, one item per wake, implement-on-branch, never merge.
- **Reviewed by the user in the morning.**

## Guardrails (re-read every wake — do not violate)
1. **Branch only.** Commit to `frontend-polishing`. Never checkout/commit `main` or `deployment-dev`. Never merge.
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
- [x] **R4 · SignUp double-submit guard.** Done `6fc09b2` — persist agentId + navigate right after `submitAgent` succeeds; the first solve is now best-effort (welcome re-solves), so a failed optimize can't strand the attendee or let a re-press create a duplicate.

### Phone
- [x] **P1 · Live holdings on the phone profile.** Done `a256e6b` — gliding allocation bar + top-6 holdings rows (ticker/pct/$, value-flash on change) + "+N more held", under the P&L block; browser-verified (28-holding a06, values move, scrolls cleanly, no overflow).
- [x] **P2 · Phone heading + landmark.** Done `dab6a9c` — agent name is now an `<h1>` (class out-specifies global h1 → no visual change, browser-verified) and the profile view is `<main>`.

### TV
- [x] **T1 · StateC live asset changes.** Done `f87388b` — per-asset 24h change seeded then drifts every 2s (clamped −6…+7%) while on screen; interval cleaned up on unmount.
- [x] **T2 · Spotlight derived labels.** Done `866be9c` — "02h 14m on the board" → the agent's real `handle` (fallback to rank); dropped the fabricated "4s ago" (no per-agent solve timestamp exists). Honest data only.
- [x] **T3 · TV landmarks + transition polish.** Done `4bb998e` — found+fixed a real bug: the rotation `setTimeout` depended on `leaderboard`, so the 4s poll reset the 12–20s timer before it fired → rotation was FROZEN on one state. Length now via ref, dep dropped; browser-confirmed A→B rotates. Added `<main>` on the stage; cross-fade reads well.

### Accessibility / production
- [x] **A1 · Landmarks everywhere.** Done `a6e2ba3` — `<main>` now on every surface (landing earlier, phone P2, TV T3, kiosk sign-up + welcome here; no global `main{}` rule so layout is unchanged). Follow-up A5 below covers heading promotion.
- [x] **A5 · Heading promotion.** Done `da0c0be` — the three kiosk step eyebrows are now `role="heading" aria-level={2}` (avoids the big global serif h2; zero visual change) with the decorative step numbers `aria-hidden`. Gives the multi-step form real SR structure under the hero `<h1>`.
- [x] **A2 · Reach-out group semantics.** Done `fc9299c` — wrapped the options in a labeled `role="group"` (it's a multi-select with one opt-out, not a radio group, so the `aria-pressed` toggles stay valid). Nuance left: "No thanks"'s clear-the-rest behavior is conveyed by interaction, not announced — a `role="radio"` split would misrepresent the multi-select, so deferred unless you want a dedicated opt-out control.
- [x] **A3 · RR v7 future flags.** Done `9851ab3` — `future={{ v7_startTransition, v7_relativeSplatPath }}` on BrowserRouter; browser-confirmed console is now clean (warnings gone) and lazy/Suspense routing still works.
- [x] **A4 · Tap targets (phone side only).** Done `187b281` — `.phone-v4 .v4m-basket-back` 28→40px; phone slider drag zone padding 10→14px (margin cancels → layout/visuals unchanged, ~track+28px touch area). Scoped to `.phone-v4`, so the fixed kiosk is untouched.

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
- 2026-06-22 · R4 kiosk create/solve decoupling → `6fc09b2` (tsc/lint/build green). Picked over R2/R3 (broader audits) as the concrete high-value win.
- 2026-06-22 · Loop paused mid-T1: concurrent backend loop held the shared working tree (branch `backend-hardening`). Backend since merged to deployment-dev; resumed on the main tree.
- 2026-06-22 · T1 StateC live asset drift → `f87388b` (tsc/lint/build green). When the backlog's implementable items are exhausted, merge this branch into deployment-dev (user-authorized; disjoint from backend).
- 2026-06-22 · P1 phone live holdings strip → `a256e6b` (browser-verified; values move, bar glides).
- 2026-06-22 · P2 phone h1 + main → `dab6a9c` (browser-verified — name unchanged).
- 2026-06-22 · T2 spotlight real handle + drop fake solve-age → `866be9c` (gate green).
- 2026-06-22 · T3 TV rotation-timer bug fix (was frozen) + <main> → `4bb998e` (browser-confirmed A→B rotates).
- 2026-06-22 · A3 RR v7 future flags → `9851ab3` (console clean, browser-verified).
- 2026-06-22 · A1 kiosk <main> (landmarks complete across surfaces) → `a6e2ba3`; split heading-promotion into A5.
- 2026-06-22 · A5 kiosk step eyebrows → headings (role=heading) → `da0c0be` (gate green, zero visual change).
- 2026-06-22 · A2 reach-out role=group label → `fc9299c` (gate green; radio-split deferred as it would misrepresent the multi-select).
- 2026-06-22 · A4 phone tap targets (basket-back 40px, slider drag zone) → `187b281` (phone-scoped; kiosk untouched).
