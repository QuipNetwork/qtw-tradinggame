// Deterministic mapping from slider values to portfolio weights.
// Ported verbatim from design-doc.html so kiosk welcome / phone profile and
// the design doc produce identical numbers for the same inputs.

import type { SliderValues } from '../api';

export const SLIDER_LABELS: ReadonlyArray<ReadonlyArray<string>> = [
  ['Minimal', 'Low', 'Medium', 'High', 'Extreme'],
  ['Conservative', 'Defensive', 'Balanced', 'Aggressive', 'Speculative'],
  ['Tiny', 'Small', 'Medium', 'Large', 'Heavy'],
];

export function labelFor(idx: number, val: number): string {
  const labels = SLIDER_LABELS[idx];
  const i = Math.min(labels.length - 1, Math.floor(val / 20));
  return labels[i];
}

// Returns [w1, w2, w3, w4, reserve]. The first four sum to (1 - reserve).
// p* are 0..1 (i.e. slider/100). Higher risk = more concentrated in the top
// holdings; lower activity / lower risk = a bigger cash reserve.
export function computeWeights(p1: number, p2: number, _p3: number): number[] {
  const concentration = p2 * 0.6;
  const top    = 0.30 + concentration * 0.40;
  const second = top * 0.72;
  const third  = top * 0.50;
  const fourth = top * 0.30;
  const sum = top + second + third + fourth;
  const reserve = Math.max(0.05, Math.min(0.25, 0.12 - p1 * 0.06 + (1 - p2) * 0.10));
  const scale = (1 - reserve) / sum;
  return [top * scale, second * scale, third * scale, fourth * scale, reserve];
}

export function slidersToArray(s: SliderValues): [number, number, number] {
  return [s.tradingActivity, s.riskPreference, s.tradeSize];
}

// The glyph engine takes five pattern parameters; with three sliders the
// last two are derived so each agent still gets a distinct pattern.
export function glyphParams(s: SliderValues) {
  const p1 = s.tradingActivity / 100;
  const p2 = s.riskPreference / 100;
  const p3 = s.tradeSize / 100;
  return { p1, p2, p3, p4: (p1 + p3) / 2, p5: (p1 + p2 + p3) / 3 };
}
