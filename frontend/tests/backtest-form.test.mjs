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
