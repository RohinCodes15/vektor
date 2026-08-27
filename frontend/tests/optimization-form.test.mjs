import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, runBacktestOptimization } from "../src/lib/api.ts";
import { mount, nodes } from "./component-runtime.mjs";

const ui = Object.fromEntries(["Badge", "Button", "Field", "Panel"].map((name) => [name, function Mock() {}]));
function MockResults() {}
async function form(client = runBacktestOptimization) {
  const hook = await mount("../src/hooks/use-backtest-optimization.ts", { "../lib/api": { ApiError, runBacktestOptimization: client } }, "useBacktestOptimization");
  const component = await mount("../src/components/optimization-form.tsx", {
    "../hooks/use-backtest-optimization": { useBacktestOptimization: () => hook.render() }, "./ui": ui, "./optimization-results": { OptimizationResults: MockResults },
  }, "OptimizationForm");
  component.render(); hook.flush();
  return { component, hook };
}
function find(component, predicate) {
  const node = nodes(component.render()).find(predicate);
  assert.ok(node); return node.props;
}
function change(component, id, value) {
  find(component, (node) => node.props?.id === `optimization-${id}`).onChange({ target: { value } });
  find(component, (node) => node.type === "form").onChange();
}
function choose(component, name, value) {
  find(component, (node) => node.props?.name === `optimization-${name}` && node.props.value === value).onChange();
  find(component, (node) => node.type === "form").onChange();
}
function submit(component) { return find(component, (node) => node.type === "form").onSubmit({ preventDefault() {} }); }
function fill(component) {
  change(component, "symbol", " aapl "); change(component, "start", "2024-01-01"); change(component, "end", "2024-12-31");
}

test("optimization offers only SMA/RSI supported parameters and chronological split bounds", async () => {
  const { component } = await form();
  assert.ok(find(component, (node) => node.props?.id === "optimization-fast"));
  assert.equal(nodes(component.render()).some((node) => node.props?.id === "optimization-periods"), false);
  choose(component, "kind", "rsi");
  for (const id of ["periods", "oversold", "overbought"]) assert.ok(find(component, (node) => node.props?.id === `optimization-${id}`));
  assert.equal(nodes(component.render()).some((node) => node.props?.id === "optimization-fast"), false);
  const train = find(component, (node) => node.props?.id === "optimization-train");
  assert.deepEqual([train.min, train.max, train.step, train.value], ["50", "90", "1", "70"]);
  assert.equal(nodes(component.render()).filter((node) => node.props?.name === "optimization-objective").length, 3);
});

test("optimization submits RSI decimal lists without rounding and supports Sharpe objective", async () => {
  let submitted;
  const { component } = await form(async (config) => { submitted = config; return { selected: {} }; });
  fill(component); choose(component, "kind", "rsi"); choose(component, "objective", "sharpe_ratio");
  change(component, "periods", " 7, 14 "); change(component, "oversold", "25.25, 30.00"); change(component, "overbought", "70.50,75");
  await submit(component);
  assert.equal(submitted.objective, "sharpe_ratio");
  assert.deepEqual(submitted.grid, { kind: "rsi", periods: [7, 14], oversold: ["25.25", "30.00"], overbought: ["70.50", "75"] });
});

test("optimization validates parameter syntax and API bounds without network requests", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  const { component } = await form(); fill(component);
  for (const [id, value, message] of [
    ["fast", "2,", /Empty entries/], ["fast", "2.5", /whole numbers/], ["fast", "abc", /whole numbers/],
    ["fast", "2,2", /distinct values/], ["fast", "1", /valid SMA or RSI grid/],
  ]) {
    change(component, id, value); await submit(component);
    assert.match(find(component, (node) => node.props?.role === "alert").children, message);
  }
  change(component, "fast", "2"); change(component, "train", "49"); await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /Training percentage/);
  change(component, "train", "70"); change(component, "end", "2024-01-01"); await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /valid dates/);
  change(component, "end", "2024-12-31"); choose(component, "kind", "rsi");
  change(component, "oversold", "30, 30.00"); await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /distinct values/);
  assert.equal(request.mock.callCount(), 0);
});

