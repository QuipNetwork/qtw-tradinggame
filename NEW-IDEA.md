# NEW-IDEA.md

## Daily-grid estimation for the cross-class (crypto + stock) book

**Status:** post-booth idea, prototyped on real data 2026-06-24. Not shipped.

### The idea
Estimate μ and Σ on a **daily business-day grid** instead of the production **hourly** grid,
so crypto (24/7) and stocks (market-hours) sit on one comparable, overnight-inclusive calendar basis.

### Why (the problem with the hourly grid)
Production estimates μ over 168h, Σ over 720h, no-fabrication (closed-hour/weekend gaps = NaN,
overnight jumps excluded). That puts the two classes on different clocks:
- Crypto ~720 hourly obs / 30d; stocks ~140 (market hours only) → cross-class covariance is built from
  only the ~140 *overlapping* US-market hours (noisier, blind to the 73% of crypto's life when stocks
  are closed).
- Per-hour μ is not calendar-comparable across classes, and **stock μ is intraday-only** — the overnight
  gap (where stocks often move: earnings, news) is excluded, so stocks are systematically understated.

### Evidence (prototype — real data)
`docs/research/scripts/qtw_daily_vs_hourly_grid.py` — same 15 booth assets, hourly (assets-api) vs daily
(Yahoo, resampled to business days), through the same select pipeline:
- **IBM μ: +68%/yr hourly (intraday-only) → +239%/yr daily (overnight-incl) — a +171pp swing.**
- Conservative stablecoin weight: **58% (hourly) → 31% (daily)**.
- Aggressive ≈ 12% stablecoins on *both* grids when positive-μ names are in the watchlist — so the
  "Aggressive → 62% stablecoins" optic was a **watchlist artifact** (all-negative-μ stocks), not a grid
  or optimizer bug.

### The key decoupling (why this is safe for the booth)
The **estimation grid and the live P&L are independent**:
- Optimizer uses μ/Σ → the **allocation** (which K assets, what weights), at solve/retune only.
- `run_mtm_loop` revalues holdings against **real spot every 10s** → the live feel, regardless of grid.
- The allocation enters at **current spot** (`holdings = w·value/spot`), so today's price is already in
  the sizing.
→ Moving estimation to daily does **not** make the booth less live; it only makes the allocation the
smarter, cross-class-comparable one.

### Implementation path (fits the booth-day infra)
- assets-api serves **hourly** bars + spot. "Daily" = resample its hourly closes → business-day closes
  server-side in `backend/.../financial/prices/assets_api.py` (or add a daily endpoint), then daily
  returns. Crypto folds the weekend into the Fri→Mon return so both classes align on the trading calendar.
- Daily windows need more calendar history for a stable Σ: μ ≈ 21–30 business days, Σ ≈ 90–120
  (≥ `MIN_RETURN_OBS`).
- Keep live P&L on real-time spot (unchanged).
- Optional recency: **EWMA-weight the daily μ** so retunes react faster — cleaner than appending a ragged
  intraday partial-day return (which mixes horizons / double-counts part of a day).

### Caveats
- Daily doesn't *fix* μ noise — μ estimation error is the weak link on any grid (DeMiguel; μ-free MaxDiv
  beat MV out-of-sample in the backtests). Daily just measures returns on an honest, comparable basis.
- Bigger change than the booth needs — this is a **post-booth** improvement.

### Smaller alternative (if a full daily rebuild is too much)
Keep the hourly grid but **stop excluding the overnight gap for stocks** (include close→open) — captures
most of the benefit (correct stock μ) without moving to daily.
