// Deterministic mapping from slider values to portfolio weights.
// Ported verbatim from design-doc.html so kiosk welcome / phone profile and
// the design doc produce identical numbers for the same inputs.

import type { SliderValues } from '../api';

export const SLIDER_LABELS: ReadonlyArray<ReadonlyArray<string>> = [
  ['Daily', 'Every 8h', 'Every 4h', 'Every 2h', 'Hourly'],
  ['Conservative', 'Defensive', 'Balanced', 'Aggressive', 'Speculative'],
  ['Tiny', 'Small', 'Medium', 'Large', 'Heavy'],
];

// Short cadence labels for the compact inline rebalance chip row (one line, so the
// strategy card stays short and the watchlist above doesn't scroll).
export const REBALANCE_CHIP_LABELS = ['Daily', '8h', '4h', '2h', 'Hourly'] as const;

// Rebalance cadence tiers (PLACEHOLDER, owned by the backend): quantum jobs
// cost real money, so the most aggressive setting is capped at one scheduled
// job per hour. Over the 2-day activation (~10 booth hours/day) that is at
// most ~20 scheduled jobs per agent, plus any manual retunes from the phone.
export const REBALANCE_TIERS = [
  { label: 'Daily',    hours: 24 },
  { label: 'Every 8h', hours: 8 },
  { label: 'Every 4h', hours: 4 },
  { label: 'Every 2h', hours: 2 },
  { label: 'Hourly',   hours: 1 },   // hard cap
] as const;

// Tier index (0..len-1) for a 0–100 rebalance slider value. Single source of the
// bucketing so the slider→hours mapping and the cadence chips can't drift apart.
export function rebalanceTierIndex(value: number): number {
  return Math.min(REBALANCE_TIERS.length - 1, Math.floor(value / 20));
}

export function rebalanceEveryHours(value: number): number {
  return REBALANCE_TIERS[rebalanceTierIndex(value)].hours;
}

// Max position size is RELATIVE to the basket: an absolute cap below 1/n
// would be infeasible (n assets can't sum to 100%), and with a big basket a
// large absolute cap never binds. The slider sweeps from equal weight across
// the basket (1/n — maximally diversified) up to ~50% in a single asset.
export function maxPositionCapPct(basketSize: number, value: number): number {
  const n = Math.max(1, basketSize);
  const floor = 1 / n;
  const ceiling = Math.max(0.5, floor);     // a 1-asset basket is always 100%
  const cap = floor + (value / 100) * (ceiling - floor);
  return Math.round(cap * 100);
}

export function labelFor(idx: number, val: number): string {
  const labels = SLIDER_LABELS[idx];
  const i = Math.min(labels.length - 1, Math.floor(val / 20));
  return labels[i];
}

// Returns [w1, w2, w3, w4, reserve]. The first four sum to (1 - reserve).
// p* are 0..1 (i.e. slider/100): p1 = rebalance frequency, p2 = risk,
// p3 = max position size. Risk concentrates the top holdings, the position
// cap bounds them, and cautious low-frequency agents hold more cash.
export function computeWeights(p1: number, p2: number, p3: number): number[] {
  const cap = 0.12 + p3 * 0.38;              // per-asset cap: 12%–50%
  const concentration = p2 * 0.6;
  const top    = Math.min(0.30 + concentration * 0.40, cap);
  const second = top * 0.72;
  const third  = top * 0.50;
  const fourth = top * 0.30;
  const sum = top + second + third + fourth;
  const reserve = Math.max(0.05, Math.min(0.25, 0.12 - p1 * 0.06 + (1 - p2) * 0.10));
  const scale = (1 - reserve) / sum;
  return [top * scale, second * scale, third * scale, fourth * scale, reserve];
}

export function slidersToArray(s: SliderValues): [number, number, number] {
  return [s.rebalanceFrequency, s.riskPreference, s.maxPositionSize];
}

// The glyph engine takes five pattern parameters; with three sliders the
// last two are derived so each agent still gets a distinct pattern.
export function glyphParams(s: SliderValues) {
  const p1 = s.rebalanceFrequency / 100;
  const p2 = s.riskPreference / 100;
  const p3 = s.maxPositionSize / 100;
  return { p1, p2, p3, p4: (p1 + p3) / 2, p5: (p1 + p2 + p3) / 3 };
}
