export type BacktestChartPoint = Readonly<{ date: string; value: number; x: number; y: number }>;

export function backtestChartGeometry(values: readonly Readonly<{ date: string; value: number }>[], width: number) {
  const plot = { left: 72, right: width - 16, top: 20, bottom: 238 };
  if (!values.length) return { points: [] as BacktestChartPoint[], path: "", valueTicks: [], dateTicks: [], plot, zeroY: null };
  let low = values[0].value;
  let high = low;
  for (const point of values) { low = Math.min(low, point.value); high = Math.max(high, point.value); }
  const padding = Math.max((high - low) * 0.08, Math.max(Math.abs(low), Math.abs(high), 1) * 0.01);
  const minimum = low - padding;
  const maximum = high + padding;
  const first = Date.parse(values[0].date);
  const last = Date.parse(values.at(-1)!.date);
  const x = (date: string): number => first === last ? (plot.left + plot.right) / 2 : plot.left + ((Date.parse(date) - first) / (last - first)) * (plot.right - plot.left);
  const y = (value: number): number => plot.bottom - ((value - minimum) / (maximum - minimum)) * (plot.bottom - plot.top);
  const points = values.map((point) => ({ ...point, x: x(point.date), y: y(point.value) }));
  const count = width < 480 ? 2 : 4;
  const indexes = [...new Set(Array.from({ length: count }, (_, index) => Math.round(index / (count - 1) * (points.length - 1))))];
  return {
    points, plot,
    path: points.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" "),
    valueTicks: Array.from({ length: 4 }, (_, index) => { const value = minimum + (maximum - minimum) * index / 3; return { value, y: y(value) }; }),
    dateTicks: indexes.map((index) => points[index]),
    zeroY: minimum <= 0 && maximum >= 0 ? y(0) : null,
  };
}

export function nearestBacktestPoint(points: readonly BacktestChartPoint[], x: number): number {
  if (!points.length) return -1;
  let left = 0, right = points.length - 1;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (points[middle].x < x) left = middle + 1;
    else right = middle;
  }
  return left > 0 && Math.abs(points[left - 1].x - x) <= Math.abs(points[left].x - x) ? left - 1 : left;
}
