export type HistoryRange = "1M" | "3M" | "6M" | "1Y" | "ALL";

export function historyRange(range: HistoryRange, now: Date = new Date()): { start: string; end: string } {
  const end = now.toISOString().slice(0, 10);
  if (range === "ALL") return { start: "1900-01-01", end };
  const start = new Date(`${end}T00:00:00Z`);
  const day = start.getUTCDate();
  start.setUTCDate(1);
  start.setUTCMonth(start.getUTCMonth() - ({ "1M": 1, "3M": 3, "6M": 6, "1Y": 12 }[range]));
  const lastDay = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
  start.setUTCDate(Math.min(day, lastDay));
  return { start: start.toISOString().slice(0, 10), end };
}
