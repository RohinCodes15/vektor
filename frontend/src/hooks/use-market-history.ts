"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getMarketHistory, type MarketHistoryQuery, type MarketHistoryResponse } from "../lib/api";

export type MarketHistoryState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: MarketHistoryResponse }
  | { status: "error"; message: string };

export function useMarketHistory(): { state: MarketHistoryState; load: (query: MarketHistoryQuery) => Promise<void> } {
  const [state, setState] = useState<MarketHistoryState>({ status: "idle" });
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  const load = useCallback(async (query: MarketHistoryQuery): Promise<void> => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setState({ status: "loading" });
    try {
      const data = await getMarketHistory(query, controller.signal);
      if (!controller.signal.aborted) setState({ status: "success", data });
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Market history request failed. Try again." });
    }
  }, []);

  return { state, load };
}
