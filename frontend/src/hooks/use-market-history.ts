"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getMarketHistory, type MarketHistoryQuery, type MarketHistoryResponse } from "../lib/api";

export type MarketHistoryState =
  | { status: "idle" }
  | { status: "loading"; query: MarketHistoryQuery }
  | { status: "success"; data: MarketHistoryResponse }
  | { status: "error"; message: string; statusCode?: number };

export function useMarketHistory(): { state: MarketHistoryState; load: (query: MarketHistoryQuery) => Promise<void> } {
  const [state, setState] = useState<MarketHistoryState>({ status: "idle" });
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  const load = useCallback(async (query: MarketHistoryQuery): Promise<void> => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setState({ status: "loading", query });
    try {
      // Let Strict Mode cleanup and same-turn symbol changes cancel before fetching.
      await Promise.resolve();
      if (controller.signal.aborted) return;
      const data = await getMarketHistory(query, controller.signal);
      if (!controller.signal.aborted) setState({ status: "success", data });
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Market history request failed. Try again.", statusCode: error instanceof ApiError ? error.statusCode : undefined });
    }
  }, []);

  return { state, load };
}
