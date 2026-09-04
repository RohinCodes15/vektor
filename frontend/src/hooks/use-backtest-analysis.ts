"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getBacktestAnalysis, type BacktestAnalysis } from "../lib/api";

export type BacktestAnalysisState =
  | { status: "idle" }
  | { status: "loading"; backtestId: string }
  | { status: "success"; data: Extract<BacktestAnalysis, { status: "available" }> }
  | { status: "unavailable"; data: Extract<BacktestAnalysis, { status: "unavailable" }> }
  | { status: "error"; backtestId: string; message: string; statusCode?: number };

export function useBacktestAnalysis(): { state: BacktestAnalysisState; load: (backtestId: string) => Promise<void> } {
  const [state, setState] = useState<BacktestAnalysisState>({ status: "idle" });
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  const load = useCallback(async (backtestId: string): Promise<void> => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setState({ status: "loading", backtestId });
    try {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      const data = await getBacktestAnalysis(backtestId, controller.signal);
      if (!controller.signal.aborted) {
        if (data.status === "available") setState({ status: "success", data });
        else setState({ status: "unavailable", data });
      }
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: "error", backtestId, message: error instanceof Error ? error.message : "Backtest analysis request failed. Try again.", statusCode: error instanceof ApiError ? error.statusCode : undefined });
    }
  }, []);

  return { state, load };
}
