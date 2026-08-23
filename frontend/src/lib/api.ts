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

async function requestJson(path: string, name: "health" | "market history" | "portfolio" | "backtest" | "backtest analysis" | "strategy comparison", signal?: AbortSignal, params?: URLSearchParams, body?: unknown): Promise<unknown> {
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

  const timeout = AbortSignal.timeout(name === "backtest analysis" ? 300000 : name === "backtest" || name === "strategy comparison" ? 30000 : 5000);
  let response: Response;
  try {
    response = await fetch(url, {
      method: name === "backtest analysis" || body !== undefined ? "POST" : "GET",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      ...(body === undefined ? {} : { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error(`Backend ${operation} timed out. Try again.`);
    throw new Error("Backend could not be reached. Check that it is running and allows this frontend origin.");
  }
  if (!response.ok) {
    if (name === "strategy comparison") {
      const messages: Record<number, string> = {
        404: "No historical data found for this comparison's symbol and date range.",
        422: "Strategy comparison was rejected. Check the strategies, symbol, dates, and costs.",
        502: "The market data provider returned invalid data. No comparison was accepted.",
        503: "The market data provider is unavailable. Try again later.",
      };
      if (messages[response.status]) throw new ApiError(messages[response.status], response.status);
    }
    if (name === "backtest analysis") {
      const messages: Record<number, string> = {
        404: "This backtest no longer exists.",
        422: "Choose a valid backtest to analyze.",
        502: "The AI provider returned an invalid analysis. No interpretation was accepted.",
        503: "The AI provider is unavailable. Try again later.",
      };
      if (messages[response.status]) throw new ApiError(messages[response.status], response.status);
    }
    if (name === "backtest") {
      const messages: Record<number, string> = {
        404: "This backtest no longer exists.",
        422: "Backtest configuration was rejected. Check the symbols, dates, strategy, and costs.",
        502: "The market data provider returned invalid data. No backtest was accepted.",
        503: "The market data provider is unavailable. Try again later.",
      };
      if (messages[response.status]) throw new ApiError(messages[response.status], response.status);
    }
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

function isSignedDecimal(value: unknown): value is string {
  return typeof value === "string" && value.length <= 128
    && /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) && Number.isFinite(Number(value));
}

export async function getPortfolioAnalytics(id: string, signal?: AbortSignal): Promise<PortfolioAnalytics> {
  if (!isUuid(id)) throw new Error("Choose a valid portfolio.");
  const data = await requestJson(`/api/v1/portfolios/${id}/analytics`, "portfolio", signal);
  if (!hasFields(data, ["portfolio_id", "currency", "as_of", "snapshots", "daily_observations", "equity", "net_deposits", "realized_pnl", "unrealized_pnl", "total_return_pct", "latest_daily_return_pct", "volatility_pct", "max_drawdown_pct", "sharpe_ratio"])
    || data.portfolio_id !== id || data.currency !== "USD"
    || typeof data.snapshots !== "number" || !Number.isSafeInteger(data.snapshots) || data.snapshots < 0
    || typeof data.daily_observations !== "number" || !Number.isSafeInteger(data.daily_observations)
    || data.daily_observations < 0 || data.daily_observations > data.snapshots
    || !(data.as_of === null || isAwareTimestamp(data.as_of))
    || (data.snapshots === 0) !== (data.as_of === null)
    || !["equity", "net_deposits", "realized_pnl", "unrealized_pnl"].every((key) => data[key] === null || isMoney(data[key], key === "equity" || key === "net_deposits"))
    || !["total_return_pct", "latest_daily_return_pct", "volatility_pct", "max_drawdown_pct", "sharpe_ratio"].every((key) => data[key] === null || isSignedDecimal(data[key]))
    || (data.volatility_pct !== null && Number(data.volatility_pct) < 0)
    || (data.max_drawdown_pct !== null && Number(data.max_drawdown_pct) > 0))
    throw new Error("Backend returned incompatible portfolio analytics. No metrics were accepted.");
  return data as PortfolioAnalytics;
}

export async function getPortfolioEquityHistory(id: string, signal?: AbortSignal): Promise<readonly EquitySnapshot[]> {
  if (!isUuid(id)) throw new Error("Choose a valid portfolio.");
  const data = await requestJson(`/api/v1/portfolios/${id}/equity-history`, "portfolio", signal);
  if (!Array.isArray(data) || !data.every((item) => hasFields(item, ["id", "portfolio_id", "taken_at", "cash", "positions_value", "equity", "net_deposits", "realized_pnl", "unrealized_pnl", "prices_as_of"])
    && isUuid(item.id) && item.portfolio_id === id && isAwareTimestamp(item.taken_at)
    && [item.cash, item.positions_value, item.equity, item.net_deposits].every((value) => isMoney(value, true))
    && isMoney(item.realized_pnl) && isMoney(item.unrealized_pnl)
    && (item.prices_as_of === null || isCalendarDate(item.prices_as_of)))
    || new Set(data.map((item) => item.id)).size !== data.length
    || data.some((item, index) => index > 0 && Date.parse(item.taken_at) < Date.parse(data[index - 1].taken_at)))
    throw new Error("Backend returned incompatible recorded equity history. No observations were accepted.");
  return data;
}

export type AssetAllocation = Readonly<{
  symbol: string; quantity: string; last_price: string | null; price_date: string | null;
  market_value: string | null; weight_pct: string | null; position_weight_pct: string | null; stale: boolean;
}>;
export type PortfolioAllocation = Readonly<{
  portfolio_id: string; currency: "USD"; valued_at: string; status: "available" | "unavailable";
  unavailable_reason: string | null; cash: string; positions_value: string | null; equity: string | null;
  cash_weight_pct: string | null; prices_as_of: string | null; unpriced_symbols: readonly string[];
  stale_symbols: readonly string[]; assets: readonly AssetAllocation[]; top_holding_symbol: string | null;
  top_holding_pct: string | null; hhi: string | null;
}>;

function isTicker(value: unknown): value is string {
  return typeof value === "string" && /^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(value);
}

function isPercentage(value: unknown): value is string {
  return isDecimal(value) && Number(value) <= 100;
}

function isMetricStatus(value: Record<string, unknown>): boolean {
  return value.status === "available" ? value.unavailable_reason === null
    : value.status === "unavailable" && typeof value.unavailable_reason === "string" && value.unavailable_reason.trim().length > 0;
}

function isAssetAllocation(value: unknown): value is AssetAllocation {
  if (!hasFields(value, ["symbol", "quantity", "last_price", "price_date", "market_value", "weight_pct", "position_weight_pct", "stale"])
    || !isTicker(value.symbol) || !isDecimal(value.quantity, true) || typeof value.stale !== "boolean"
    || !(value.weight_pct === null || isPercentage(value.weight_pct))
    || !(value.position_weight_pct === null || isPercentage(value.position_weight_pct))) return false;
  return value.last_price === null ? value.price_date === null && value.market_value === null && value.weight_pct === null && value.position_weight_pct === null
    : isDecimal(value.last_price, true) && isCalendarDate(value.price_date) && isMoney(value.market_value, true);
}

export async function getPortfolioAllocation(id: string, signal?: AbortSignal): Promise<PortfolioAllocation> {
  if (!isUuid(id)) throw new Error("Choose a valid portfolio.");
  const data = await requestJson(`/api/v1/portfolios/${id}/allocation`, "portfolio", signal);
  if (!hasFields(data, ["portfolio_id", "currency", "valued_at", "status", "unavailable_reason", "cash", "positions_value", "equity", "cash_weight_pct", "prices_as_of", "unpriced_symbols", "stale_symbols", "assets", "top_holding_symbol", "top_holding_pct", "hhi"])
    || data.portfolio_id !== id || data.currency !== "USD" || !isAwareTimestamp(data.valued_at) || !isMetricStatus(data)
    || !isMoney(data.cash, true) || !(data.positions_value === null || isMoney(data.positions_value, true))
    || !(data.equity === null || isMoney(data.equity, true)) || !(data.cash_weight_pct === null || isPercentage(data.cash_weight_pct))
    || !(data.prices_as_of === null || isCalendarDate(data.prices_as_of))
    || !Array.isArray(data.assets) || !data.assets.every(isAssetAllocation)
    || new Set(data.assets.map((asset) => asset.symbol)).size !== data.assets.length
    || ![data.unpriced_symbols, data.stale_symbols].every((symbols) => Array.isArray(symbols) && symbols.every(isTicker) && new Set(symbols).size === symbols.length && symbols.every((symbol) => (data.assets as AssetAllocation[]).some((asset) => asset.symbol === symbol)))
    || !(data.top_holding_symbol === null || isTicker(data.top_holding_symbol) && data.assets.some((asset) => asset.symbol === data.top_holding_symbol))
    || !(data.top_holding_pct === null || isPercentage(data.top_holding_pct))
    || !(data.hhi === null || isDecimal(data.hhi) && Number(data.hhi) <= 1))
    throw new Error("Backend returned incompatible portfolio allocation. No weights were accepted.");
  if (data.status === "available" && (data.cash_weight_pct === null || data.top_holding_symbol === null || data.top_holding_pct === null || data.hhi === null || data.assets.some((asset) => asset.weight_pct === null || asset.position_weight_pct === null))
    || (data.unpriced_symbols as string[]).length > 0 && (data.equity !== null || data.cash_weight_pct !== null || data.assets.some((asset) => asset.weight_pct !== null || asset.position_weight_pct !== null)))
    throw new Error("Backend returned inconsistent allocation availability. No weights were accepted.");
  return data as PortfolioAllocation;
}

export type AssetRisk = Readonly<{
  symbol: string; weight_pct: string; volatility_pct: string;
  volatility_contribution_pct: string | null; contribution_share_pct: string | null;
}>;
export type AssetCorrelation = Readonly<{ symbol_a: string; symbol_b: string; correlation: string | null }>;
export type PortfolioRisk = Readonly<{
  portfolio_id: string; currency: "USD"; valued_at: string; status: "available" | "unavailable";
  unavailable_reason: string | null; window_start: string; window_end: string;
  observations: number; min_observations: number; returns_as_of: string | null;
  portfolio_volatility_pct: string | null; assets: readonly AssetRisk[]; correlations: readonly AssetCorrelation[];
}>;

function isAssetRisk(value: unknown): value is AssetRisk {
  return hasFields(value, ["symbol", "weight_pct", "volatility_pct", "volatility_contribution_pct", "contribution_share_pct"])
    && isTicker(value.symbol) && isPercentage(value.weight_pct) && isDecimal(value.volatility_pct)
    && (value.volatility_contribution_pct === null || isSignedDecimal(value.volatility_contribution_pct))
    && (value.contribution_share_pct === null || isSignedDecimal(value.contribution_share_pct));
}

export async function getPortfolioRisk(id: string, signal?: AbortSignal): Promise<PortfolioRisk> {
  if (!isUuid(id)) throw new Error("Choose a valid portfolio.");
  const data = await requestJson(`/api/v1/portfolios/${id}/risk`, "portfolio", signal);
  if (!hasFields(data, ["portfolio_id", "currency", "valued_at", "status", "unavailable_reason", "window_start", "window_end", "observations", "min_observations", "returns_as_of", "portfolio_volatility_pct", "assets", "correlations"])
    || data.portfolio_id !== id || data.currency !== "USD" || !isAwareTimestamp(data.valued_at) || !isMetricStatus(data)
    || !isCalendarDate(data.window_start) || !isCalendarDate(data.window_end) || data.window_start > data.window_end
    || typeof data.observations !== "number" || !Number.isSafeInteger(data.observations) || data.observations < 0
    || typeof data.min_observations !== "number" || !Number.isSafeInteger(data.min_observations) || data.min_observations < 1
    || !(data.returns_as_of === null || isCalendarDate(data.returns_as_of))
    || !(data.portfolio_volatility_pct === null || isDecimal(data.portfolio_volatility_pct))
    || !Array.isArray(data.assets) || !data.assets.every(isAssetRisk) || new Set(data.assets.map((asset) => asset.symbol)).size !== data.assets.length
    || !Array.isArray(data.correlations) || !data.correlations.every((pair) => hasFields(pair, ["symbol_a", "symbol_b", "correlation"])
      && (data.assets as AssetRisk[]).some((asset) => asset.symbol === pair.symbol_a) && (data.assets as AssetRisk[]).some((asset) => asset.symbol === pair.symbol_b)
      && (pair.correlation === null || isSignedDecimal(pair.correlation) && Math.abs(Number(pair.correlation)) <= 1))
    || new Set(data.correlations.map((pair) => `${pair.symbol_a}:${pair.symbol_b}`)).size !== data.correlations.length
    || (data.status === "available" && (data.portfolio_volatility_pct === null || data.returns_as_of === null || data.observations < data.min_observations))
    || (data.status === "unavailable" && (data.portfolio_volatility_pct !== null || data.assets.length > 0 || data.correlations.length > 0)))
    throw new Error("Backend returned incompatible portfolio risk. No risk metrics were accepted.");
  return data as PortfolioRisk;
}

/** Mirrors Phase 2G.1. Decimal values stay as exact JSON strings. */
export type BacktestStrategy =
  | Readonly<{ kind: "buy_and_hold" }>
  | Readonly<{ kind: "sma_crossover"; fast_window?: number; slow_window?: number }>
  | Readonly<{ kind: "rsi"; period?: number; oversold?: string; overbought?: string }>;
export type BacktestCreate = Readonly<{
  symbols: readonly string[]; start: string; end: string; starting_cash: string; strategy: BacktestStrategy;
  position_size_pct?: string; fee_per_trade?: string; fee_bps?: string; slippage_bps?: string;
}>;
export type BacktestConfig = Readonly<{
  symbols: readonly string[]; start: string; end: string; starting_cash: string;
  strategy: Readonly<{ kind: "buy_and_hold" }>
    | Readonly<{ kind: "sma_crossover"; fast_window: number; slow_window: number }>
    | Readonly<{ kind: "rsi"; period: number; oversold: string; overbought: string }>;
  position_size_pct: string; fee_per_trade: string; fee_bps: string; slippage_bps: string;
}>;
export type BacktestMetrics = Readonly<{
  final_equity: string; total_return_pct: string; annualized_return_pct: string | null;
  volatility_pct: string | null; max_drawdown_pct: string; sharpe_ratio: string | null;
  win_rate_pct: string | null; trades: number; closed_trades: number; winning_trades: number; total_fees: string;
}>;
export type BacktestTrade = Readonly<{
  symbol: string; side: "buy" | "sell"; signal_date: string; fill_date: string; quantity: number;
  price: string; notional: string; fee: string; realized_pnl: string | null;
}>;
export type BacktestRejectedOrder = Readonly<{
  symbol: string; side: "buy" | "sell"; signal_date: string; fill_date: string; reason: string;
}>;
export type BacktestEquityPoint = Readonly<{
  date: string; cash: string; positions_value: string; equity: string; drawdown_pct: string;
}>;
export type BacktestPosition = Readonly<{
  symbol: string; quantity: number; cost_basis: string; last_price: string; market_value: string; unrealized_pnl: string;
}>;
export type Backtest = Readonly<{
  id: string; mode: "paper"; currency: "USD"; config: BacktestConfig; created_at: string;
  source: "yahoo_finance"; bars: number; first_date: string; last_date: string; metrics: BacktestMetrics;
  warnings: readonly string[]; equity_curve: readonly BacktestEquityPoint[]; trades: readonly BacktestTrade[];
  rejected_orders: readonly BacktestRejectedOrder[]; open_positions: readonly BacktestPosition[];
}>;

function isBoundedDecimal(value: unknown, minimum: number, maximum: number, places = 2): value is string {
  if (typeof value !== "string" || !/^\d+(?:\.\d+)?$/.test(value)) return false;
  const fraction = value.split(".")[1];
  const number = Number(value);
  return (!fraction || fraction.length <= places) && Number.isFinite(number) && number >= minimum && number <= maximum;
}

function normalizeBacktestCreate(config: BacktestCreate): BacktestCreate {
  if (!Array.isArray(config.symbols) || config.symbols.length < 1 || config.symbols.length > 10) throw new Error("Choose 1 to 10 symbols.");
  const symbols = config.symbols.map((symbol) => typeof symbol === "string" ? symbol.trim().toUpperCase() : "");
  if (!symbols.every(isTicker) || new Set(symbols).size !== symbols.length) throw new Error("Use 1 to 10 distinct tradable symbols.");
  const today = new Date().toISOString().slice(0, 10);
  if (!isCalendarDate(config.start) || !isCalendarDate(config.end) || config.start >= config.end || config.end >= today)
    throw new Error("Choose valid dates with start before end and end before today (UTC).");
  if (!isBoundedDecimal(config.starting_cash, Number.MIN_VALUE, 999999999999.99)) throw new Error("Starting cash must be positive with at most 2 decimal places.");
  if (config.position_size_pct !== undefined && !isBoundedDecimal(config.position_size_pct, Number.MIN_VALUE, 100)) throw new Error("Position size must be greater than 0 and at most 100%.");
  if (config.fee_per_trade !== undefined && !isBoundedDecimal(config.fee_per_trade, 0, 1000)) throw new Error("Fee per trade must be between 0 and 1000.");
  for (const value of [config.fee_bps, config.slippage_bps]) {
    if (value !== undefined && !isBoundedDecimal(value, 0, 1000)) throw new Error("Fee and slippage basis points must be between 0 and 1000.");
  }
  const strategy = config.strategy;
  if (strategy.kind === "sma_crossover") {
    const fast = strategy.fast_window ?? 20, slow = strategy.slow_window ?? 50;
    if (!Number.isInteger(fast) || fast < 2 || fast > 250 || !Number.isInteger(slow) || slow < 3 || slow > 500 || fast >= slow)
      throw new Error("SMA windows must be valid and fast must be smaller than slow.");
  } else if (strategy.kind === "rsi") {
    const period = strategy.period ?? 14, oversold = strategy.oversold ?? "30", overbought = strategy.overbought ?? "70";
    if (!Number.isInteger(period) || period < 2 || period > 100 || !isBoundedDecimal(oversold, Number.MIN_VALUE, 99.99)
      || !isBoundedDecimal(overbought, Number.MIN_VALUE, 99.99) || Number(oversold) >= Number(overbought))
      throw new Error("RSI settings must be valid and oversold must be below overbought.");
  } else if (strategy.kind !== "buy_and_hold") throw new Error("Choose a supported backtest strategy.");
  return { ...config, symbols };
}

function isBacktestConfig(value: unknown): value is BacktestConfig {
  const today = new Date().toISOString().slice(0, 10);
  if (!hasFields(value, ["symbols", "start", "end", "starting_cash", "strategy", "position_size_pct", "fee_per_trade", "fee_bps", "slippage_bps"])
    || !Array.isArray(value.symbols) || value.symbols.length < 1 || value.symbols.length > 10 || !value.symbols.every(isTicker)
    || new Set(value.symbols).size !== value.symbols.length || !isCalendarDate(value.start) || !isCalendarDate(value.end)
    || value.start >= value.end || value.end >= today || !isBoundedDecimal(value.starting_cash, Number.MIN_VALUE, 999999999999.99)
    || !isBoundedDecimal(value.position_size_pct, Number.MIN_VALUE, 100) || !isBoundedDecimal(value.fee_per_trade, 0, 1000)
    || !isBoundedDecimal(value.fee_bps, 0, 1000) || !isBoundedDecimal(value.slippage_bps, 0, 1000)
    || typeof value.strategy !== "object" || value.strategy === null || Array.isArray(value.strategy)) return false;
  const strategy = value.strategy as Record<string, unknown>;
  return strategy.kind === "buy_and_hold" ? hasFields(strategy, ["kind"])
    : strategy.kind === "sma_crossover" ? hasFields(strategy, ["kind", "fast_window", "slow_window"])
      && Number.isInteger(strategy.fast_window) && (strategy.fast_window as number) >= 2 && (strategy.fast_window as number) <= 250
      && Number.isInteger(strategy.slow_window) && (strategy.slow_window as number) >= 3 && (strategy.slow_window as number) <= 500
      && (strategy.fast_window as number) < (strategy.slow_window as number)
    : strategy.kind === "rsi" && hasFields(strategy, ["kind", "period", "oversold", "overbought"])
      && Number.isInteger(strategy.period) && (strategy.period as number) >= 2 && (strategy.period as number) <= 100
      && isBoundedDecimal(strategy.oversold, Number.MIN_VALUE, 99.99) && isBoundedDecimal(strategy.overbought, Number.MIN_VALUE, 99.99)
      && Number(strategy.oversold) < Number(strategy.overbought);
}

function isBacktestMetrics(value: unknown): value is BacktestMetrics {
  if (!hasFields(value, ["final_equity", "total_return_pct", "annualized_return_pct", "volatility_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate_pct", "trades", "closed_trades", "winning_trades", "total_fees"])) return false;
  return isMoney(value.final_equity, true) && isSignedDecimal(value.total_return_pct) && isSignedDecimal(value.max_drawdown_pct)
    && Number(value.max_drawdown_pct) <= 0 && (value.annualized_return_pct === null || isSignedDecimal(value.annualized_return_pct))
    && (value.volatility_pct === null || isDecimal(value.volatility_pct)) && (value.sharpe_ratio === null || isSignedDecimal(value.sharpe_ratio))
    && (value.win_rate_pct === null || isPercentage(value.win_rate_pct))
    && [value.trades, value.closed_trades, value.winning_trades].every((item) => Number.isSafeInteger(item) && (item as number) >= 0)
    && (value.closed_trades as number) <= (value.trades as number) && (value.winning_trades as number) <= (value.closed_trades as number) && isMoney(value.total_fees, true);
}

function isBacktest(value: unknown): value is Backtest {
  if (!hasFields(value, ["id", "mode", "currency", "config", "created_at", "source", "bars", "first_date", "last_date", "metrics", "warnings", "equity_curve", "trades", "rejected_orders", "open_positions"])
    || !isUuid(value.id) || value.mode !== "paper" || value.currency !== "USD" || !isBacktestConfig(value.config)
    || !isAwareTimestamp(value.created_at) || value.source !== "yahoo_finance" || !Number.isSafeInteger(value.bars) || (value.bars as number) < 1
    || !isCalendarDate(value.first_date) || !isCalendarDate(value.last_date) || value.first_date > value.last_date || !isBacktestMetrics(value.metrics)
    || !Array.isArray(value.warnings) || !value.warnings.every((warning) => typeof warning === "string") || !Array.isArray(value.equity_curve)
    || !Array.isArray(value.trades) || !Array.isArray(value.rejected_orders) || !Array.isArray(value.open_positions)) return false;
  if (value.equity_curve.length !== value.bars || value.metrics.trades !== value.trades.length
    || value.equity_curve[0]?.date !== value.first_date || value.equity_curve.at(-1)?.date !== value.last_date) return false;
  let previousDate = "";
  return value.equity_curve.every((point) => {
    const valid = hasFields(point, ["date", "cash", "positions_value", "equity", "drawdown_pct"])
      && isCalendarDate(point.date) && point.date > previousDate && isMoney(point.cash, true)
      && isMoney(point.positions_value, true) && isMoney(point.equity, true)
      && isSignedDecimal(point.drawdown_pct) && Number(point.drawdown_pct) <= 0;
    if (valid) previousDate = point.date as string;
    return valid;
  })
    && value.trades.every((trade) => hasFields(trade, ["symbol", "side", "signal_date", "fill_date", "quantity", "price", "notional", "fee", "realized_pnl"])
      && isTicker(trade.symbol) && (trade.side === "buy" || trade.side === "sell") && isCalendarDate(trade.signal_date) && isCalendarDate(trade.fill_date)
      && Number.isSafeInteger(trade.quantity) && (trade.quantity as number) > 0 && isDecimal(trade.price, true) && isMoney(trade.notional, true) && isMoney(trade.fee, true)
      && (trade.side === "buy" ? trade.realized_pnl === null : isMoney(trade.realized_pnl)))
    && value.rejected_orders.every((order) => hasFields(order, ["symbol", "side", "signal_date", "fill_date", "reason"])
      && isTicker(order.symbol) && (order.side === "buy" || order.side === "sell") && isCalendarDate(order.signal_date) && isCalendarDate(order.fill_date) && typeof order.reason === "string")
    && value.open_positions.every((position) => hasFields(position, ["symbol", "quantity", "cost_basis", "last_price", "market_value", "unrealized_pnl"])
      && isTicker(position.symbol) && Number.isSafeInteger(position.quantity) && (position.quantity as number) > 0 && isMoney(position.cost_basis, true)
      && isDecimal(position.last_price, true) && isMoney(position.market_value, true) && isMoney(position.unrealized_pnl));
}

export async function runBacktest(config: BacktestCreate, signal?: AbortSignal): Promise<Backtest> {
  const data = await requestJson("/api/v1/backtests", "backtest", signal, undefined, normalizeBacktestCreate(config));
  if (!isBacktest(data)) throw new Error("Backend returned an incompatible backtest result. No simulation data was accepted.");
  return data;
}

export type BacktestComparisonCreate = Omit<BacktestCreate, "symbols" | "strategy"> & Readonly<{
  symbol: string; strategies: readonly BacktestStrategy[];
}>;
export type BacktestComparisonConfig = Omit<BacktestConfig, "symbols" | "strategy"> & Readonly<{
  symbol: string; strategies: readonly BacktestConfig["strategy"][];
}>;
const comparisonMetrics = ["total_return_pct", "annualized_return_pct", "volatility_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate_pct"] as const;
export type ComparisonMetric = typeof comparisonMetrics[number];
export type MetricDifferences = Readonly<Record<ComparisonMetric, string | null>>;
export type StrategyComparisonResult = Readonly<{ strategy: BacktestConfig["strategy"]; warnings: readonly string[] }> & Readonly<
  | { status: "available"; unavailable_reason: null; metrics: BacktestMetrics; equity: readonly string[]; vs_baseline: MetricDifferences | null }
  | { status: "unavailable"; unavailable_reason: string; metrics: null; equity: null; vs_baseline: null }
>;
export type MetricLeader = Readonly<{ metric: ComparisonMetric; better: "higher" | "lower"; leaders: readonly number[]; reason: string | null }>;
export type BacktestComparison = Readonly<{
  mode: "paper"; currency: "USD"; source: "yahoo_finance"; config: BacktestComparisonConfig;
  bars: number; first_date: string; last_date: string; dates: readonly string[];
  results: readonly StrategyComparisonResult[]; leaders: readonly MetricLeader[]; disclaimer: string;
}>;

function strategyKey(strategy: BacktestStrategy): string {
  return JSON.stringify(strategy.kind === "sma_crossover" ? [strategy.kind, strategy.fast_window ?? 20, strategy.slow_window ?? 50]
    : strategy.kind === "rsi" ? [strategy.kind, strategy.period ?? 14, Number(strategy.oversold ?? "30"), Number(strategy.overbought ?? "70")]
    : [strategy.kind]);
}

function normalizeComparisonCreate(config: BacktestComparisonCreate): BacktestComparisonCreate {
  if (!Array.isArray(config.strategies) || config.strategies.length < 2 || config.strategies.length > 5)
    throw new Error("Choose 2 to 5 distinct strategies.");
  const { symbol, strategies, ...settings } = config;
  const normalized = strategies.map((strategy) => normalizeBacktestCreate({ ...settings, symbols: [symbol], strategy }));
  if (new Set(normalized.map((item) => strategyKey(item.strategy))).size !== strategies.length)
    throw new Error("Choose distinct strategies with different kinds or parameters.");
  return { ...settings, symbol: normalized[0].symbols[0], strategies };
}

function isComparisonConfig(value: unknown): value is BacktestComparisonConfig {
  if (!hasFields(value, ["symbol", "strategies", "start", "end", "starting_cash", "position_size_pct", "fee_per_trade", "fee_bps", "slippage_bps"])
    || !Array.isArray(value.strategies) || value.strategies.length < 2 || value.strategies.length > 5) return false;
  const { symbol, strategies, ...settings } = value;
  return strategies.every((strategy) => isBacktestConfig({ ...settings, symbols: [symbol], strategy }))
    && new Set(strategies.map(strategyKey)).size === strategies.length;
}

function isBacktestComparison(value: unknown, query: BacktestComparisonCreate): value is BacktestComparison {
  if (!hasFields(value, ["mode", "currency", "source", "config", "bars", "first_date", "last_date", "dates", "results", "leaders", "disclaimer"])
    || value.mode !== "paper" || value.currency !== "USD" || value.source !== "yahoo_finance" || !isComparisonConfig(value.config)
    || typeof value.disclaimer !== "string" || !value.disclaimer.trim() || !Number.isSafeInteger(value.bars) || (value.bars as number) < 1
    || !Array.isArray(value.dates) || value.dates.length !== value.bars || !value.dates.every(isCalendarDate)
    || value.first_date !== value.dates[0] || value.last_date !== value.dates.at(-1)
    || value.dates.some((date, index, dates) => date < query.start || date > query.end || (index > 0 && date <= dates[index - 1]))
    || !Array.isArray(value.results) || value.results.length !== query.strategies.length || !Array.isArray(value.leaders)) return false;
  const config = value.config;
  if (config.symbol !== query.symbol || config.start !== query.start || config.end !== query.end
    || Number(config.starting_cash) !== Number(query.starting_cash)
    || Number(config.position_size_pct) !== Number(query.position_size_pct ?? "100")
    || (["fee_per_trade", "fee_bps", "slippage_bps"] as const).some((key) => Number(config[key]) !== Number(query[key] ?? "0"))
    || config.strategies.length !== query.strategies.length || config.strategies.some((strategy, index) => strategyKey(strategy) !== strategyKey(query.strategies[index]))) return false;
  const baseline = value.results[0];
  if (!value.results.every((result, index) => {
    if (!hasFields(result, ["strategy", "status", "unavailable_reason", "metrics", "warnings", "equity", "vs_baseline"])
      || !isBacktestConfig({ symbols: [config.symbol], start: config.start, end: config.end, starting_cash: config.starting_cash,
        position_size_pct: config.position_size_pct, fee_per_trade: config.fee_per_trade, fee_bps: config.fee_bps, slippage_bps: config.slippage_bps, strategy: result.strategy })
      || strategyKey(result.strategy as BacktestStrategy) !== strategyKey(config.strategies[index])
      || !Array.isArray(result.warnings) || !result.warnings.every((warning) => typeof warning === "string")) return false;
    if (result.status === "unavailable") return typeof result.unavailable_reason === "string" && !!result.unavailable_reason.trim()
      && result.metrics === null && result.equity === null && result.vs_baseline === null;
    if (result.status !== "available" || result.unavailable_reason !== null || !isBacktestMetrics(result.metrics)
      || !Array.isArray(result.equity) || result.equity.length !== value.bars || !result.equity.every((equity) => isMoney(equity, true))) return false;
    const metrics = result.metrics;
    if (baseline?.status === "unavailable") return result.vs_baseline === null;
    if (!hasFields(result.vs_baseline, comparisonMetrics)) return false;
    const differences = result.vs_baseline;
    return comparisonMetrics.every((metric) => metrics[metric] === null || baseline?.metrics?.[metric] === null
      ? differences[metric] === null : isSignedDecimal(differences[metric]));
  })) return false;
  const results = value.results as StrategyComparisonResult[];
  return new Set(value.leaders.map((leader) => leader?.metric)).size === value.leaders.length
    && value.leaders.every((leader) => hasFields(leader, ["metric", "better", "leaders", "reason"])
      && comparisonMetrics.includes(leader.metric as ComparisonMetric)
      && leader.better === (leader.metric === "volatility_pct" ? "lower" : "higher") && Array.isArray(leader.leaders)
      && new Set(leader.leaders).size === leader.leaders.length
      && (leader.leaders.length === 0 ? typeof leader.reason === "string" && !!leader.reason.trim() : leader.reason === null)
      && leader.leaders.every((index) => Number.isSafeInteger(index) && index >= 0 && index < results.length
        && results[index].status === "available" && results[index].metrics?.[leader.metric as ComparisonMetric] !== null));
}

export async function runBacktestComparison(config: BacktestComparisonCreate, signal?: AbortSignal): Promise<BacktestComparison> {
  const query = normalizeComparisonCreate(config);
  const data = await requestJson("/api/v1/backtests/comparisons", "strategy comparison", signal, undefined, query);
  if (!isBacktestComparison(data, query)) throw new Error("Backend returned an incompatible strategy comparison. No comparison data was accepted.");
  return data;
}

export type AnalysisFact = Readonly<{ id: string; label: string; value: string }>;
export type AnalysisInsight = Readonly<{ text: string; evidence: readonly string[] }>;
export type AnalysisInterpretation = Readonly<{
  summary: string; strategy_behavior: readonly AnalysisInsight[]; strengths: readonly AnalysisInsight[];
  weaknesses: readonly AnalysisInsight[]; risk_factors: readonly AnalysisInsight[]; limitations: readonly AnalysisInsight[];
}>;
export type BacktestAnalysis = Readonly<{
  backtest_id: string; mode: "paper"; generated_at: string; facts: readonly AnalysisFact[]; disclaimer: string;
}> & Readonly<
  | { status: "available"; unavailable_reason: null; provider: "anthropic"; model: string; interpretation: AnalysisInterpretation }
  | { status: "unavailable"; unavailable_reason: string; provider: null; model: null; interpretation: null }
>;

function isAnalysisInterpretation(value: unknown, factIds: ReadonlySet<string>): value is AnalysisInterpretation {
  if (!hasFields(value, ["summary", "strategy_behavior", "strengths", "weaknesses", "risk_factors", "limitations"])
    || typeof value.summary !== "string" || value.summary.length < 1 || value.summary.length > 800) return false;
  return ["strategy_behavior", "strengths", "weaknesses", "risk_factors", "limitations"].every((key) => {
    const insights = value[key];
    return Array.isArray(insights) && insights.length <= 5
      && (!(key === "strategy_behavior" || key === "limitations") || insights.length >= 1)
      && insights.every((insight) => hasFields(insight, ["text", "evidence"])
        && typeof insight.text === "string" && insight.text.length >= 1 && insight.text.length <= 600
        && Array.isArray(insight.evidence) && insight.evidence.length >= 1 && insight.evidence.length <= 6
        && insight.evidence.every((id) => typeof id === "string" && factIds.has(id)));
  });
}

function isBacktestAnalysis(value: unknown, id: string): value is BacktestAnalysis {
  if (!hasFields(value, ["backtest_id", "mode", "status", "unavailable_reason", "generated_at", "provider", "model", "facts", "interpretation", "disclaimer"])
    || typeof value.backtest_id !== "string" || value.backtest_id.toLowerCase() !== id.toLowerCase() || value.mode !== "paper"
    || !isAwareTimestamp(value.generated_at) || typeof value.disclaimer !== "string" || !value.disclaimer.trim()
    || !Array.isArray(value.facts) || !value.facts.every((fact) => hasFields(fact, ["id", "label", "value"])
      && typeof fact.id === "string" && typeof fact.label === "string" && typeof fact.value === "string")) return false;
  const factIds = new Set<string>(value.facts.map((fact) => fact.id));
  if (factIds.size !== value.facts.length) return false;
  if (value.status === "unavailable") return typeof value.unavailable_reason === "string" && !!value.unavailable_reason.trim()
    && value.provider === null && value.model === null && value.interpretation === null;
  return value.status === "available" && value.unavailable_reason === null && value.provider === "anthropic"
    && typeof value.model === "string" && !!value.model.trim() && isAnalysisInterpretation(value.interpretation, factIds);
}

export async function getBacktestAnalysis(id: string, signal?: AbortSignal): Promise<BacktestAnalysis> {
  if (!isUuid(id)) throw new Error("Choose a valid backtest to analyze.");
  const data = await requestJson(`/api/v1/backtests/${id}/analysis`, "backtest analysis", signal);
  if (!isBacktestAnalysis(data, id)) throw new Error("Backend returned an incompatible backtest analysis. No analysis was accepted.");
  return data;
}
