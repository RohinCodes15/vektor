import type { PriceBar } from "./api";

export type ChartPoint = Readonly<{ x: number; y: number; date: string; close: number }>;

/** Calendar spacing preserves gaps; only provider observations become plotted points. */
export function priceChartGeometry(bars: readonly Pick<PriceBar, "date" | "close">[], width: number) {
  const plot = { left: 72, right: width - 16, top: 20, bottom: 238 };
  if (!bars.length) return { points: [] as ChartPoint[], path: "", priceTicks: [], dateTicks: [], plot };
  let low = bars[0].close;
  let high = low;
  for (const bar of bars) { low = Math.min(low, bar.close); high = Math.max(high, bar.close); }
  const padding = Math.max((high - low) * 0.08, high * 0.01, Number.MIN_VALUE);
  const minimum = Math.max(0, low - padding);
  const maximum = Math.min(Number.MAX_VALUE, high + padding);
  const first = Date.parse(bars[0].date);
  const last = Date.parse(bars[bars.length - 1].date);
  const x = (date: string): number => first === last ? (plot.left + plot.right) / 2 : plot.left + ((Date.parse(date) - first) / (last - first)) * (plot.right - plot.left);
  const y = (price: number): number => plot.bottom - ((price - minimum) / (maximum - minimum)) * (plot.bottom - plot.top);
  const points = bars.map((bar) => ({ date: bar.date, close: bar.close, x: x(bar.date), y: y(bar.close) }));
  const count = width < 480 ? 2 : 4;
  const indexes = [...new Set(Array.from({ length: count }, (_, index) => Math.round((index / (count - 1)) * (points.length - 1))))];
  return {
    points, plot,
    path: points.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" "),
    priceTicks: Array.from({ length: 4 }, (_, index) => { const value = minimum + (maximum - minimum) * (index / 3); return { value, y: y(value) }; }),
    dateTicks: indexes.map((index) => points[index]),
  };
}

export function nearestChartPoint(points: readonly ChartPoint[], x: number): number {
  if (!points.length) return -1;
  let left = 0;
  let right = points.length - 1;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (points[middle].x < x) left = middle + 1;
    else right = middle;
  }
  return left > 0 && Math.abs(points[left - 1].x - x) <= Math.abs(points[left].x - x) ? left - 1 : left;
}

export function formatChartPrice(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumSignificantDigits: 6, notation: value > 0 && (value < 0.0001 || value >= 1e9) ? "scientific" : "standard" }).format(value);
}
