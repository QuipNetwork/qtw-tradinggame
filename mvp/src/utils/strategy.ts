// Deterministic mapping from slider values to portfolio weights.
// Ported verbatim from summary.html so kiosk welcome / phone profile and
// the design doc produce identical numbers for the same inputs.

import type { SliderValues } from '../api';

export const SLIDER_LABELS: ReadonlyArray<ReadonlyArray<string>> = [
  ['Minimal', 'Low', 'Medium', 'High', 'Extreme'],
  ['Conservative', 'Defensive', 'Balanced', 'Aggressive', 'Speculative'],
  ['Tiny', 'Small', 'Medium', 'Large', 'Heavy'],
  ['Restless', 'Quick', 'Balanced', 'Patient', 'Diamond'],
  ['Concentrated', 'Focused', 'Balanced', 'Spread', 'Wide'],
];

export function labelFor(idx: number, val: number): string {
  const labels = SLIDER_LABELS[idx];
  const i = Math.min(labels.length - 1, Math.floor(val / 20));
  return labels[i];
}

// Returns [BTC, ETH, SOL, USDC, reserve]. The first four sum to (1 - reserve).
// p* are 0..1 (i.e. slider/100). p3 and p4 are part of the contract but
// unused in the current formula — kept for parity with summary.html.
export function computeWeights(p1: number, p2: number, _p3: number, _p4: number, p5: number): number[] {
  const concentration = Math.max(0, p2 - p5 * 0.5);
  const top    = 0.30 + concentration * 0.40;
  const second = top * (0.65 + p5 * 0.15);
  const third  = top * (0.40 + p5 * 0.20);
  const fourth = top * (0.20 + p5 * 0.20);
  const sum = top + second + third + fourth;
  const reserve = Math.max(0.05, Math.min(0.25, 0.12 - p1 * 0.06 + (1 - p2) * 0.10));
  const scale = (1 - reserve) / sum;
  return [top * scale, second * scale, third * scale, fourth * scale, reserve];
}

export function slidersToArray(s: SliderValues): [number, number, number, number, number] {
  return [s.tradingActivity, s.riskPreference, s.tradeSize, s.holdingStyle, s.diversification];
}
