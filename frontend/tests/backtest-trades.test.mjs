import { test } from "node:test";
import assert from "node:assert/strict";
import { formatMoney } from "../src/lib/portfolio-values.ts";
import { mount, nodes } from "./component-runtime.mjs";

const ui = Object.fromEntries(["Badge", "Panel"].map((name) => [name, function Mock(props) { return { type: name, props }; }]));
const trades = [
  { symbol: "MSFT", side: "sell", signal_date: "2024-01-04", fill_date: "2024-01-05", quantity: 5, price: "110.2500", notional: "551.25", fee: "1.25", realized_pnl: "25.00" },
  { symbol: "AAPL", side: "buy", signal_date: "2024-01-01", fill_date: "2024-01-02", quantity: 12, price: "100.1234", notional: "1201.48", fee: "1.00", realized_pnl: null },
  { symbol: "AAPL", side: "sell", signal_date: "2024-01-02", fill_date: "2024-01-03", quantity: 12, price: "99.5000", notional: "1194.00", fee: "1.00", realized_pnl: "-9.48" },
];

async function componentFor(input) {
  return mount("../src/components/backtest-trades.tsx", { "../lib/api": {}, "../lib/portfolio-values": { formatMoney }, "./ui": ui }, "BacktestTrades", { trades: input });
}

function rows(tree) {
  return nodes(tree).filter((node) => node.type === "tbody")[0].props.children;
}

test("trade table shows exact real fill fields and unavailable buy P&L", async () => {
  const component = await componentFor(trades);
  const tree = component.render();
  const text = JSON.stringify(tree);
  for (const value of ["2024-01-02", "AAPL", "BUY", "12", "100.1234", "$1.00", "$25.00", "−$9.48"]) assert.ok(text.includes(value), value);
  assert.ok(nodes(tree).some((node) => node.type === "td" && Array.isArray(node.props.children) && node.props.children.join("") === "$100.1234"));
  assert.ok(nodes(tree).some((node) => node.props?.["aria-label"] === "Not available"));
  assert.match(nodes(tree).find((node) => node.type === "caption").props.children.flat(Infinity).join(""), /3 simulated fills/);
});
