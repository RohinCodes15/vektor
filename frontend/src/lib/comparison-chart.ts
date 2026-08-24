import type { BacktestConfig } from "./api.ts";
import { backtestChartGeometry } from "./backtest-chart.ts";

export function comparisonStrategyLabel(strategy: BacktestConfig["strategy"]): string {
  return strategy.kind === "buy_and_hold" ? "Buy & Hold" : strategy.kind === "sma_crossover"
    ? `SMA ${strategy.fast_window}/${strategy.slow_window}` : `RSI ${strategy.period} · ${strategy.oversold}/${strategy.overbought}`;
}

export function comparisonChartGeometry(dates: readonly string[], series: readonly (readonly string[] | null)[], width: number) {
  const aligned = series.map((values) => values !== null && values.length === dates.length
    && values.every((value) => typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) >= 0));
  const observations = series.flatMap((values, seriesIndex) => aligned[seriesIndex]
    ? values!.map((value, index) => ({ date: dates[index], value: Number(value), seriesIndex })) : []);
  observations.sort((a, b) => a.date.localeCompare(b.date));
  const geometry = backtestChartGeometry(observations, width);
  const curves = series.map((_, seriesIndex) => geometry.points.filter((point, index) => observations[index].seriesIndex === seriesIndex));
  return { ...geometry, aligned, curves, dateTicks: [...new Map(geometry.dateTicks.map((tick) => [tick.date, tick])).values()] };
}
