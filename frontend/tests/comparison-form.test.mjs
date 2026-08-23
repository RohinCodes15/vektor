import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { runBacktestComparison } from "../src/lib/api.ts";

const ui = Object.fromEntries(["Badge", "Button", "Field", "Panel"].map((name) => [name, function Mock() {}]));
async function form(client = runBacktestComparison) {
  return mount("../src/components/comparison-form.tsx", { "../lib/api": { runBacktestComparison: client }, "./ui": ui }, "ComparisonForm");
}
function find(component, predicate) {
  const node = nodes(component.render()).find(predicate);
  assert.ok(node);
  return node.props;
}
function field(component, id, value) {
  find(component, (node) => node.props?.id === id).onChange({ target: { value } });
}
function radio(component, row, kind) {
  find(component, (node) => node.props?.name === `comparison-kind-${row}` && node.props.value === kind).onChange();
}
function submit(component) {
  return find(component, (node) => node.type === "form").onSubmit({ preventDefault() {} });
}
function button(component, label) {
  return find(component, (node) => node.type === ui.Button && node.props.children === label);
}
function fill(component) {
  for (const [id, value] of [["symbol", " aapl "], ["start", "2024-01-01"], ["end", "2024-12-31"]]) field(component, `comparison-${id}`, value);
}
const available = { strategy: { kind: "buy_and_hold" }, status: "available" };
const unavailable = { strategy: { kind: "sma_crossover" }, status: "unavailable", unavailable_reason: "Too few daily bars for warm-up." };

test("comparison edits supported parameters and keeps 2–5 stable strategy rows", async () => {
  const component = await form();
  assert.equal(find(component, (node) => node.props?.["aria-label"] === "Remove strategy 1").disabled, true);
  assert.equal(nodes(component.render()).some((node) => node.props?.id === "comparison-period-0"), false);
  radio(component, 0, "rsi");
  for (const key of ["period", "oversold", "overbought"]) assert.ok(find(component, (node) => node.props?.id === `comparison-${key}-0`));
  radio(component, 0, "sma_crossover");
  field(component, "comparison-fast-0", "10");
  field(component, "comparison-slow-0", "30");
  for (let i = 0; i < 3; i++) button(component, "Add strategy").onClick();
  assert.equal(button(component, "Add strategy").disabled, true);
  assert.equal(nodes(component.render()).filter((node) => node.props?.className === "comparison-strategy").length, 5);
  find(component, (node) => node.props?.["aria-label"] === "Remove strategy 2").onClick();
  assert.equal(button(component, "Add strategy").disabled, false);
  assert.equal(find(component, (node) => node.props?.id === "comparison-fast-0").value, "10");
  assert.ok(find(component, (node) => node.props?.id === "comparison-period-2"));
});

test("comparison submits exact shared settings and parameters, locks pending work, and retains success", async () => {
  let resolve, submitted, signal, calls = 0;
  const component = await form((config, abortSignal) => { calls++; submitted = config; signal = abortSignal; return new Promise((done) => { resolve = done; }); });
  component.render(); component.flush(); fill(component);
  field(component, "comparison-capital", "5000.00");
  field(component, "comparison-fee", "1.25");
  field(component, "comparison-fee-bps", "2.50");
  field(component, "comparison-slippage", "3.25");
  radio(component, 1, "rsi");
  field(component, "comparison-period-1", "10");
  field(component, "comparison-oversold-1", "25");
  field(component, "comparison-overbought-1", "75");
  const pending = submit(component);
  await submit(component);
  assert.equal(calls, 1);
  assert.equal(button(component, "Comparing…").disabled, true);
  assert.equal(find(component, (node) => node.type === "form")["aria-busy"], true);
  assert.equal(find(component, (node) => node.props?.id === "comparison-symbol").disabled, true);
  assert.deepEqual(submitted, { symbol: " aapl ", start: "2024-01-01", end: "2024-12-31", starting_cash: "5000.00", fee_per_trade: "1.25", fee_bps: "2.50", slippage_bps: "3.25", strategies: [{ kind: "buy_and_hold" }, { kind: "rsi", period: 10, oversold: "25", overbought: "75" }] });
  assert.equal(signal.aborted, false);
  resolve({ results: [available, available] });
  await pending;
  assert.ok(nodes(component.render()).some((node) => node.props?.children === "Comparison complete."));
  assert.equal(button(component, "Compare").disabled, false);
  field(component, "comparison-capital", "6000.00");
  assert.equal(nodes(component.render()).some((node) => node.props?.className === "comparison-status"), false);
});

test("comparison reuses client validation to reject duplicates, invalid parameters, dates, and costs before fetching", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  const component = await form(); component.render(); fill(component);
  radio(component, 1, "buy_and_hold");
  await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /distinct strategies/);
  radio(component, 1, "sma_crossover");
  field(component, "comparison-fast-1", "50"); field(component, "comparison-slow-1", "20");
  await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /SMA windows/);
  field(component, "comparison-fast-1", "10"); field(component, "comparison-slow-1", "30");
  field(component, "comparison-end", "2024-01-01");
  await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /valid dates/);
  field(component, "comparison-end", "2024-12-31"); field(component, "comparison-fee-bps", "1001");
  await submit(component);
  assert.match(find(component, (node) => node.props?.role === "alert").children, /basis points/);
  assert.equal(request.mock.callCount(), 0);
});

test("comparison reports partial and complete insufficient data and clears stale success on errors", async () => {
  let response = { results: [available, unavailable] };
  const component = await form(async () => { if (response instanceof Error) throw response; return response; });
  await submit(component);
  assert.ok(nodes(component.render()).some((node) => node.props?.children === "Insufficient data for a full comparison."));
  assert.ok(nodes(component.render()).some((node) => Array.isArray(node.props?.children) && node.props.children.includes(unavailable.unavailable_reason)));
  response = { results: [unavailable, unavailable] };
  await submit(component);
  assert.equal(nodes(component.render()).filter((node) => Array.isArray(node.props?.children) && node.props.children.includes(unavailable.unavailable_reason)).length, 2);
  response = new Error("The market data provider is unavailable.");
  await submit(component);
  assert.equal(find(component, (node) => node.props?.role === "alert").children, response.message);
  assert.equal(nodes(component.render()).some((node) => node.props?.className === "comparison-status"), false);
});

test("comparison cancels on unmount and ignores late results", async () => {
  let signal, resolve;
  const component = await form((_config, abortSignal) => { signal = abortSignal; return new Promise((done) => { resolve = done; }); });
  component.render(); component.flush();
  const pending = submit(component);
  component.unmount();
  assert.equal(signal.aborted, true);
  resolve({ results: [available, available] });
  await pending;
  assert.equal(find(component, (node) => node.type === "form")["aria-busy"], true);
});
