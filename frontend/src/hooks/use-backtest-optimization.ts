"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, runBacktestOptimization, type BacktestOptimization, type BacktestOptimizationCreate } from "../lib/api";

export type OptimizationState =
  | { status: "idle" }
  | { status: "loading"; config: BacktestOptimizationCreate }
  | { status: "success" | "insufficient-data"; data: BacktestOptimization }
  | { status: "error"; message: string; statusCode?: number };

export function useBacktestOptimization(): { state: OptimizationState; load: (config: BacktestOptimizationCreate) => Promise<void> } {
  const [state, setState] = useState<OptimizationState>({ status: "idle" });
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const load = useCallback(async (config: BacktestOptimizationCreate): Promise<void> => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setState({ status: "loading", config });
    try {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      const data = await runBacktestOptimization(config, controller.signal);
      if (!controller.signal.aborted) setState({ status: data.selected === null ? "insufficient-data" : "success", data });
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Optimization failed. Try again.", statusCode: error instanceof ApiError ? error.statusCode : undefined });
    }
  }, []);
  return { state, load };
}
