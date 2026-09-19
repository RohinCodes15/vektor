/** Mirrors backend/app/contracts.py HealthResponse; no contract changes. */
export type HealthResponse = Readonly<{
  status: "ok";
  app: string;
  version: string;
  environment: string;
  trading_mode: "paper";
}>;

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const keys = ["status", "app", "version", "environment", "trading_mode"];
  return Object.keys(record).length === keys.length
    && keys.every((key) => Object.hasOwn(record, key))
    && record.status === "ok"
    && record.trading_mode === "paper"
    && typeof record.app === "string"
    && typeof record.version === "string"
    && typeof record.environment === "string";
}

export class ApiError extends Error {
  readonly statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
  }
}

async function requestJson(path: string, name: "health" | "market history", signal?: AbortSignal, params?: URLSearchParams): Promise<unknown> {
  const operation = name === "health" ? "health check" : "market history request";
  let url: URL;
  try {
    url = new URL(process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000");
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error();
    url.pathname = path;
    if (params) url.search = params.toString();
  } catch {
    throw new Error("Backend address is invalid. Check NEXT_PUBLIC_API_ORIGIN.");
  }

  const timeout = AbortSignal.timeout(5000);
  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error(`Backend ${operation} timed out. Try again.`);
    throw new Error("Backend could not be reached. Check that it is running and allows this frontend origin.");
  }
  if (!response.ok) {
    if (name === "market history") {
      const messages: Record<number, string> = {
        404: "No historical data found for this symbol and date range.",
        422: "Market history query was rejected. Check the symbol and dates.",
        502: "The market data provider returned invalid data. No history was accepted.",
        503: "The market data provider is unavailable. Try again later.",
      };
      if (messages[response.status]) throw new ApiError(messages[response.status], response.status);
    }
    throw new ApiError(`Backend ${operation} failed (HTTP ${response.status}). Try again.`, response.status);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error(`Backend ${operation} timed out. Try again.`);
    throw new Error(`Backend returned an invalid ${name} response.`);
  }
  return data;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const data = await requestJson("/api/v1/health", "health", signal);
  if (!isHealthResponse(data)) throw new Error("Backend returned an incompatible health response. Expected a healthy paper-only service.");
  return data;
}

/** Inclusive calendar dates in YYYY-MM-DD format; only daily history is supported. */
export type MarketHistoryQuery = Readonly<{ symbol: string; start: string; end: string; interval?: "1d" }>;
export type PriceBar = Readonly<{
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adjusted_close: number;
  volume: number;
}>;
export type MarketHistoryResponse = Readonly<{
  symbol: string;
  interval: "1d";
  start: string;
  end: string;
  currency: string | null;
  source: "yahoo_finance";
  cached: boolean;
  fetched_at: string;
  bars: readonly PriceBar[];
}>;

function hasFields(value: unknown, fields: readonly string[]): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    && Object.keys(value).length === fields.length && fields.every((field) => Object.hasOwn(value, field));
}

function isCalendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function isAwareTimestamp(value: unknown): value is string {
  return typeof value === "string" && isCalendarDate(value.slice(0, 10))
    && /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function isPriceBar(value: unknown): value is PriceBar {
  if (!hasFields(value, ["date", "open", "high", "low", "close", "adjusted_close", "volume"]) || !isCalendarDate(value.date)) return false;
  const { open, high, low, close, adjusted_close, volume } = value;
  return typeof open === "number" && typeof high === "number" && typeof low === "number" && typeof close === "number"
    && [open, high, low, close, adjusted_close].every((price) => typeof price === "number" && Number.isFinite(price) && price > 0)
    && typeof volume === "number" && Number.isSafeInteger(volume) && volume >= 0
    && low <= Math.min(open, close) && Math.max(open, close) <= high;
}

function isMarketHistoryResponse(value: unknown, query: MarketHistoryQuery): value is MarketHistoryResponse {
  if (!hasFields(value, ["symbol", "interval", "start", "end", "currency", "source", "cached", "fetched_at", "bars"])) return false;
  if (value.symbol !== query.symbol || value.interval !== "1d" || value.start !== query.start || value.end !== query.end
    || (value.currency !== null && typeof value.currency !== "string") || value.source !== "yahoo_finance"
    || typeof value.cached !== "boolean" || !isAwareTimestamp(value.fetched_at) || !Array.isArray(value.bars)) return false;
  let previous = "";
  for (const bar of value.bars) {
    if (!isPriceBar(bar) || bar.date <= previous || bar.date < query.start || bar.date > query.end) return false;
    previous = bar.date;
  }
  return true;
}

export function normalizeMarketSymbol(value: string): string {
  const symbol = typeof value === "string" ? value.trim().toUpperCase() : "";
  if (!/^\^?[A-Z0-9][A-Z0-9.=-]{0,14}$/.test(symbol)) throw new Error("Enter a valid market symbol (1–15 characters, optionally prefixed with ^).");
  return symbol;
}

export async function getMarketHistory(query: MarketHistoryQuery, signal?: AbortSignal): Promise<MarketHistoryResponse> {
  const symbol = normalizeMarketSymbol(query.symbol);
  if (!isCalendarDate(query.start) || !isCalendarDate(query.end)) throw new Error("Enter valid start and end dates in YYYY-MM-DD format.");
  if (query.start > query.end) throw new Error("Start date must be on or before end date.");
  if (query.start > new Date().toISOString().slice(0, 10)) throw new Error("Start date cannot be in the future.");
  if (query.interval !== undefined && query.interval !== "1d") throw new Error("Only daily market history is supported.");
  const normalized = { ...query, symbol };
  const params = new URLSearchParams({ symbol, start: query.start, end: query.end, interval: "1d" });
  const data = await requestJson("/api/v1/market/history", "market history", signal, params);
  if (!isMarketHistoryResponse(data, normalized)) throw new Error("Backend returned an incompatible market history response. No data was accepted.");
  return data;
}
