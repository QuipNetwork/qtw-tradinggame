// Shared display formatters, hoisted so the kiosk welcome and phone profile
// format money identically.

export const WHOLE_USD = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

// Whole-dollar amount with the leading "$" (e.g. 11401.7 → "$11,402").
export function fmtUsd(n: number): string {
  return `$${WHOLE_USD.format(Math.round(n))}`;
}
