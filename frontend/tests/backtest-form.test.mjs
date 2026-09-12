import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";

const ui = Object.fromEntries(["Badge", "Button", "Field", "Panel"].map((name) => [name, function Mock(props) { return { type: name, props }; }]));

function find(tree, predicate) {
  const node = nodes(tree).find(predicate);
  assert.ok(node);
  return node;
}

test("backtest form shows only selected strategy parameters", async () => {
  const component = await mount("../src/components/backtest-form.tsx", { "../lib/api": { runBacktest() {} }, "./ui": ui }, "BacktestForm");
  let tree = component.render();
  assert.ok(find(tree, (node) => node.props?.id === "backtest-symbol"));
  assert.equal(nodes(tree).some((node) => node.props?.id === "backtest-fast-window"), false);
  find(tree, (node) => node.props?.value === "sma_crossover").props.onChange();
  tree = component.render();
  assert.ok(find(tree, (node) => node.props?.id === "backtest-fast-window"));
  assert.ok(find(tree, (node) => node.props?.id === "backtest-slow-window"));
  assert.equal(nodes(tree).some((node) => node.props?.id === "backtest-rsi-period"), false);
  find(tree, (node) => node.props?.value === "rsi").props.onChange();
  tree = component.render();
  for (const id of ["backtest-rsi-period", "backtest-oversold", "backtest-overbought"]) assert.ok(find(tree, (node) => node.props?.id === id));
});

test("backtest form submits API configuration and reports loading and success", async () => {
  let submitted;
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const component = await mount("../src/components/backtest-form.tsx", { "../lib/api": { runBacktest(config) { submitted = config; return pending; } }, "./ui": ui }, "BacktestForm");
  let tree = component.render();
  for (const [id, value] of [["backtest-symbol", " aapl "], ["backtest-start", "2024-01-01"], ["backtest-end", "2024-12-31"]]) {
    find(tree, (node) => node.props?.id === id).props.onChange({ target: { value } });
  }
  tree = component.render();
  const submitting = find(tree, (node) => node.type === "form").props.onSubmit({ preventDefault() {} });
  tree = component.render();
  assert.equal(find(tree, (node) => node.props?.type === "submit").props.disabled, true);
  assert.equal(find(tree, (node) => node.props?.type === "submit").props.children, "Running backtest…");
  assert.deepEqual(submitted, {
    symbols: [" aapl "], start: "2024-01-01", end: "2024-12-31", starting_cash: "10000.00",
    strategy: { kind: "buy_and_hold" }, fee_per_trade: "0.00", fee_bps: "0", slippage_bps: "0",
  });
  resolve({ bars: 252, config: { symbols: ["AAPL"] } });
  await submitting;
  tree = component.render();
  assert.equal(find(tree, (node) => node.type === "strong").props.children, "Backtest complete.");
  assert.equal(find(tree, (node) => node.props?.type === "submit").props.disabled, false);
});
