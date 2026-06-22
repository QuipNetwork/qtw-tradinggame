// Deterministic mapping from slider values to portfolio weights.
// Ported verbatim from design-doc.html so kiosk welcome / phone profile and
// the design doc produce identical numbers for the same inputs.

import type { SliderValues } from '../api';

// Slider value labels. Row 0 (rebalance) is bucketed by REBALANCE_TIERS via the
// labelFor() special-case below, not by these strings — kept here only so the
// row indices (0 = rebalance, 1 = risk, 2 = max-position) stay aligned.
export const SLIDER_LABELS: ReadonlyArray<ReadonlyArray<string>> = [
  ['Off', '12h', '8h', '4h', '2h', '1h', '30m'],
  ['Conservative', 'Defensive', 'Balanced', 'Aggressive', 'Speculative'],
  ['Tiny', 'Small', 'Medium', 'Large', 'Heavy'],
];

// Rebalance cadence tiers. `Off` = no scheduled rebalance (the initial allocation
// rides untouched, hours = null); `30m` is the most aggressive tier.
// NOTE — backend reconciliation owed: the solver budget documents *Hourly* as a
// hard cap because QPU solves cost real money (token bucket, see CLAUDE.md and
// the qpu-budget-design note). `Off` and the sub-hourly `30m` are frontend tiers
// the kiosk/phone now offer; when the real backend is wired (mvp/src/api is on
// mocks today) the scheduler must reconcile 30m + Off with that QPU budget.
export const REBALANCE_TIERS = [
  { label: 'Off', hours: null },
  { label: '12h', hours: 12 },
  { label: '8h',  hours: 8 },
  { label: '4h',  hours: 4 },
  { label: '2h',  hours: 2 },
  { label: '1h',  hours: 1 },
  { label: '30m', hours: 0.5 },
] as const;

// Tier index (0..len-1) for a 0–100 rebalance slider value, and its inverse.
// Single source of the bucketing so the slider, the cadence labels and the
// hours mapping can't drift apart. value→index rounds onto the nearest of the
// N evenly-spaced tier stops (Off=0 … 30m=100).
export function rebalanceTierIndex(value: number): number {
  const last = REBALANCE_TIERS.length - 1;
  return Math.max(0, Math.min(last, Math.round((value / 100) * last)));
}

export function rebalanceTierValue(index: number): number {
  const last = REBALANCE_TIERS.length - 1;
  return Math.round((Math.max(0, Math.min(last, index)) / last) * 100);
}

// Hours between scheduled rebalances for a slider value, or null when Off.
export function rebalanceEveryHours(value: number): number | null {
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
  // Rebalance (row 0) buckets onto the 7 cadence tiers; the other rows keep
  // their 5-step quintile bucketing.
  if (idx === 0) return REBALANCE_TIERS[rebalanceTierIndex(val)].label;
  const labels = SLIDER_LABELS[idx];
  const i = Math.min(labels.length - 1, Math.floor(val / 20));
  return labels[i];
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
