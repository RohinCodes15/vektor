export const id = "00000000-0000-4000-8000-000000000001";
export const other = "00000000-0000-4000-8000-000000000002";
export const allocation = {
  portfolio_id: id, currency: "USD", valued_at: "2026-11-06T12:00:00Z", status: "available", unavailable_reason: null,
  cash: "400.00", positions_value: "600.00", equity: "1000.00", cash_weight_pct: "40.0000", prices_as_of: "2026-11-05",
  unpriced_symbols: [], stale_symbols: [], top_holding_symbol: "AAPL", top_holding_pct: "66.6667", hhi: "0.5556",
  assets: [
    { symbol: "AAPL", quantity: "4", last_price: "100.0000", price_date: "2026-11-05", market_value: "400.00", weight_pct: "40.0000", position_weight_pct: "66.6667", stale: false },
    { symbol: "MSFT", quantity: "1", last_price: "200.0000", price_date: "2026-11-05", market_value: "200.00", weight_pct: "20.0000", position_weight_pct: "33.3333", stale: false },
  ],
};
export const cashOnly = { ...allocation, status: "unavailable", unavailable_reason: "No open positions.", cash: "400.00", positions_value: "0.00", equity: "400.00", cash_weight_pct: "100.0000", assets: [], prices_as_of: null, top_holding_symbol: null, top_holding_pct: null, hhi: null };
export const unpriced = { ...allocation, status: "unavailable", unavailable_reason: "A holding has no recent price.", positions_value: null, equity: null, cash_weight_pct: null, top_holding_symbol: null, top_holding_pct: null, hhi: null, unpriced_symbols: ["AAPL"], assets: allocation.assets.map((asset, index) => ({ ...asset, ...(index === 0 ? { last_price: null, price_date: null, market_value: null } : {}), weight_pct: null, position_weight_pct: null })) };
export const risk = {
  portfolio_id: id, currency: "USD", valued_at: "2026-11-06T12:00:00Z", status: "available", unavailable_reason: null,
  window_start: "2026-07-09", window_end: "2026-11-05", observations: 30, min_observations: 20, returns_as_of: "2026-11-05", portfolio_volatility_pct: "7.0000",
  assets: [
    { symbol: "AAPL", weight_pct: "40.0000", volatility_pct: "20.0000", volatility_contribution_pct: "8.0000", contribution_share_pct: "114.2857" },
    { symbol: "MSFT", weight_pct: "20.0000", volatility_pct: "25.0000", volatility_contribution_pct: "-1.0000", contribution_share_pct: "-14.2857" },
  ],
  correlations: [{ symbol_a: "AAPL", symbol_b: "MSFT", correlation: "-0.2000" }],
};
export const unavailableRisk = { ...risk, status: "unavailable", unavailable_reason: "Insufficient aligned history.", observations: 5, portfolio_volatility_pct: null, assets: [], correlations: [] };
