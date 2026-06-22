// Shared display formatters, hoisted so the kiosk welcome and phone profile
// format money identically.

export const WHOLE_USD = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
