import { moneyInCents } from "./portfolio-values.ts";

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

async function requestJson(path: string, name: "health" | "market history" | "portfolio", signal?: AbortSignal, params?: URLSearchParams): Promise<unknown> {
  const operation = name === "health" ? "health check" : `${name} request`;
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
    if (name === "portfolio") {
      const messages: Record<number, string> = {
        404: "This portfolio no longer exists. Refresh the portfolio list.",
        502: "The market data provider returned invalid prices. Portfolio valuation is unavailable.",
        503: "The market data provider is unavailable. Try again later.",
      };
      if (messages[response.status]) throw new ApiError(messages[response.status], response.status);
    }
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


/** Mirrors the read-only Phase 2C contracts. Decimal values are JSON strings. */
export type Portfolio = Readonly<{
  id: string; name: string; mode: "paper"; currency: "USD";
  starting_cash: string; cash: string; realized_pnl: string; created_at: string; updated_at: string;
}>;
export type Holding = Readonly<{
  symbol: string; quantity: string; cost_basis: string; last_price: string | null;
  price_date: string | null; market_value: string | null; unrealized_pnl: string | null; allocation_pct: string | null;
}>;
export type PortfolioHoldings = Readonly<{
  portfolio_id: string; currency: "USD"; cash: string; positions_value: string | null;
  equity: string | null; unrealized_pnl: string | null; realized_pnl: string;
  cash_allocation_pct: string | null; valued_at: string; holdings: readonly Holding[];
}>;

function isUuid(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function isMoney(value: unknown, nonnegative = false): value is string {
  if (typeof value !== "string") return false;
  try { const cents = moneyInCents(value); return !nonnegative || cents >= BigInt(0); }
  catch { return false; }
}

function isDecimal(value: unknown, positive = false): value is string {
  return typeof value === "string" && value.length <= 128
    && /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value)
    && Number.isFinite(Number(value)) && (positive ? Number(value) > 0 : Number(value) >= 0);
}

function isPortfolio(value: unknown): value is Portfolio {
  return hasFields(value, ["id", "name", "mode", "currency", "starting_cash", "cash", "realized_pnl", "created_at", "updated_at"])
    && isUuid(value.id) && typeof value.name === "string" && value.name.trim().length > 0
    && value.mode === "paper" && value.currency === "USD" && isMoney(value.starting_cash, true)
    && isMoney(value.cash, true) && isMoney(value.realized_pnl)
    && isAwareTimestamp(value.created_at) && isAwareTimestamp(value.updated_at);
}

function isHolding(value: unknown): value is Holding {
  if (!hasFields(value, ["symbol", "quantity", "cost_basis", "last_price", "price_date", "market_value", "unrealized_pnl", "allocation_pct"])) return false;
  if (typeof value.symbol !== "string" || !/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(value.symbol)
    || !isDecimal(value.quantity, true) || !isMoney(value.cost_basis, true)
    || !(value.allocation_pct === null || isDecimal(value.allocation_pct))) return false;
  if (value.last_price === null) return value.price_date === null && value.market_value === null && value.unrealized_pnl === null && value.allocation_pct === null;
  return isDecimal(value.last_price, true) && isCalendarDate(value.price_date)
    && isMoney(value.market_value, true) && isMoney(value.unrealized_pnl);
}

export async function getPortfolios(signal?: AbortSignal): Promise<readonly Portfolio[]> {
  const data = await requestJson("/api/v1/portfolios", "portfolio", signal);
  if (!Array.isArray(data) || !data.every(isPortfolio) || new Set(data.map((item) => item.id)).size !== data.length)
    throw new Error("Backend returned an incompatible paper portfolio list. No balances were accepted.");
  return data;
}

export async function getPortfolioHoldings(id: string, signal?: AbortSignal): Promise<PortfolioHoldings> {
  if (!isUuid(id)) throw new Error("Choose a valid portfolio.");
  const data = await requestJson(`/api/v1/portfolios/${id}/holdings`, "portfolio", signal);
  if (!hasFields(data, ["portfolio_id", "currency", "cash", "positions_value", "equity", "unrealized_pnl", "realized_pnl", "cash_allocation_pct", "valued_at", "holdings"])
    || data.portfolio_id !== id || data.currency !== "USD" || !isMoney(data.cash, true) || !isMoney(data.realized_pnl)
    || !isAwareTimestamp(data.valued_at) || !Array.isArray(data.holdings) || !data.holdings.every(isHolding)
    || new Set(data.holdings.map((item) => item.symbol)).size !== data.holdings.length
    || !(data.cash_allocation_pct === null || isDecimal(data.cash_allocation_pct))
    || !(data.positions_value === null || isMoney(data.positions_value, true))
    || !(data.equity === null || isMoney(data.equity, true))
    || !(data.unrealized_pnl === null || isMoney(data.unrealized_pnl)))
    throw new Error("Backend returned an incompatible portfolio valuation. No balances were accepted.");
  const unpriced = data.holdings.some((holding) => holding.last_price === null);
  if (unpriced ? data.equity !== null || data.positions_value !== null || data.unrealized_pnl !== null
    || data.cash_allocation_pct !== null || data.holdings.some((holding) => holding.allocation_pct !== null)
    : data.equity === null || data.positions_value === null || data.unrealized_pnl === null)
    throw new Error("Backend returned inconsistent portfolio pricing. No balances were accepted.");
  return data as PortfolioHoldings;
}

export type Transaction = Readonly<{
  id: string; portfolio_id: string; client_order_id: string; symbol: string;
  side: "buy" | "sell"; quantity: string; price: string; price_date: string;
  notional: string; realized_pnl: string | null; executed_at: string;
}>;

export async function getPortfolioTransactions(id: string, signal?: AbortSignal): Promise<readonly Transaction[]> {
  if (!isUuid(id)) throw new Error("Choose a valid portfolio.");
  const data = await requestJson(`/api/v1/portfolios/${id}/transactions`, "portfolio", signal);
  if (!Array.isArray(data) || !data.every((item) =>
    hasFields(item, ["id", "portfolio_id", "client_order_id", "symbol", "side", "quantity", "price", "price_date", "notional", "realized_pnl", "executed_at"])
    && isUuid(item.id) && item.portfolio_id === id
    && typeof item.client_order_id === "string" && /^[A-Za-z0-9_.:-]{1,64}$/.test(item.client_order_id)
    && typeof item.symbol === "string" && /^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(item.symbol)
    && (item.side === "buy" || item.side === "sell") && isDecimal(item.quantity, true)
    && isDecimal(item.price, true) && isCalendarDate(item.price_date) && isMoney(item.notional, true)
    && (item.side === "buy" ? item.realized_pnl === null : isMoney(item.realized_pnl))
    && isAwareTimestamp(item.executed_at)) || new Set(data.map((item) => item.id)).size !== data.length)
    throw new Error("Backend returned incompatible paper transactions. No trade history was accepted.");
  return data;
}

export type EquitySnapshot = Readonly<{
  id: string; portfolio_id: string; taken_at: string; cash: string; positions_value: string;
  equity: string; net_deposits: string; realized_pnl: string; unrealized_pnl: string; prices_as_of: string | null;
}>;
export type PortfolioAnalytics = Readonly<{
  portfolio_id: string; currency: "USD"; as_of: string | null; snapshots: number; daily_observations: number;
  equity: string | null; net_deposits: string | null; realized_pnl: string | null; unrealized_pnl: string | null;
  total_return_pct: string | null; latest_daily_return_pct: string | null; volatility_pct: string | null;
  max_drawdown_pct: string | null; sharpe_ratio: string | null;
}>;
