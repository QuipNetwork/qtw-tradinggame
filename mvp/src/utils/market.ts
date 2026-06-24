// US equity regular-session hours, computed client-side so the phone profile can
// flag "Stock Market Closed" without a backend signal. Crypto trades 24/7, so this
// only governs the stock side of a basket.
//
// Regular session: Monday–Friday, 09:30–16:00 America/New_York. The Eastern
// wall-clock is read via Intl (EST/EDT resolves automatically for the instant).
// Market holidays are intentionally not modelled — booth scope.

const OPEN_MINUTE = 9 * 60 + 30; // 09:30 ET
const CLOSE_MINUTE = 16 * 60; // 16:00 ET

const WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

let cachedFormatter: Intl.DateTimeFormat | null = null;
function easternFormatter(): Intl.DateTimeFormat {
  if (!cachedFormatter) {
    cachedFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }
  return cachedFormatter;
}

// Eastern weekday (0=Sun…6=Sat) and minutes-since-midnight for an instant.
function easternParts(nowMs: number): { weekday: number; minutes: number } {
  const parts = easternFormatter().formatToParts(new Date(nowMs));
  let weekday = 0;
  let hour = 0;
  let minute = 0;
  for (const p of parts) {
    if (p.type === 'weekday') weekday = WEEKDAY_INDEX[p.value] ?? 0;
    else if (p.type === 'hour') hour = parseInt(p.value, 10) % 24; // normalize a '24' midnight
    else if (p.type === 'minute') minute = parseInt(p.value, 10);
  }
  return { weekday, minutes: hour * 60 + minute };
}

// True only during the regular US equity session. NaN/parse failures fall through
// to false (closed), the safe default for the indicator.
export function isUsStockMarketOpen(nowMs: number = Date.now()): boolean {
  const { weekday, minutes } = easternParts(nowMs);
  const isWeekday = weekday >= 1 && weekday <= 5;
  return isWeekday && minutes >= OPEN_MINUTE && minutes < CLOSE_MINUTE;
}
