// Pure mark-to-market math for the offline simulator. Mirrors the backend
// (backend/src/backend/financial/pnl.py): holdings are fixed token units between
// retunes, so the portfolio value drifts purely as spot prices move. Kept
// dependency-free and side-effect-free so it can be unit-tested and reused.

import type { AssetTicker, HoldingUpdate } from '../api/types';

export type Units = Record<string, number>;
export type Spot = Record<string, number>;

// The simulator's base price. The absolute level is irrelevant — only the
// percentage drift matters — so every asset starts here and the units carry the
// dollar weight from the allocation.
export const SIM_BASE_SPOT = 100;

//   unitsᵢ = usdᵢ / spotᵢ        (fixed between retunes — the model never trades)
export function deriveUnits(
  holdings: Array<{ ticker: string; usd: number }>,
  spot: Spot,
): Units {
  const units: Units = {};
  for (const h of holdings) {
    const s = spot[h.ticker] ?? SIM_BASE_SPOT;
    units[h.ticker] = s > 0 ? h.usd / s : 0;
  }
  return units;
}

//   total = Σ unitsᵢ·spotᵢ ;  plUSD = total − bankroll ;  pctᵢ = usdᵢ / total · 100
// Holdings come back weight-sorted (largest first), matching the backend shape.
export function markToMarket(
  units: Units,
  spot: Spot,
  bankroll: number,
): { total: number; plUSD: number; plPct: number; holdings: HoldingUpdate[] } {
  const values = Object.entries(units).map(([ticker, u]) => {
    const s = spot[ticker] ?? 0;
    return { ticker: ticker as AssetTicker, units: u, spot: s, usd: u * s };
  });
  const total = values.reduce((sum, v) => sum + v.usd, 0);
  const plUSD = total - bankroll;
  const plPct = bankroll ? (plUSD / bankroll) * 100 : 0;
  const holdings: HoldingUpdate[] = values
    .map(v => ({ ...v, pct: total ? (v.usd / total) * 100 : 0 }))
    .sort((a, b) => b.usd - a.usd);
  return { total, plUSD, plPct, holdings };
}

// One vol-scaled multiplicative random-walk step for a single spot price.
// `rand` returns [0,1) and is injectable so tests are deterministic. Sigma is
// tuned so booth motion reads as alive, not frantic: ~±0.08% (stablecoins) up to
// ~±0.5% (the most volatile names) per tick.
export function driftSpot(spot: number, vol: number, rand: () => number): number {
  const sigma = 0.0008 + Math.max(0, Math.min(1, vol)) * 0.004;
  const shock = (rand() * 2 - 1) * sigma;
  return Math.max(0.01, spot * (1 + shock));
}
