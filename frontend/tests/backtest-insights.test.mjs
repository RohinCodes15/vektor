import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { ApiError } from "../src/lib/api.ts";

const id = "123e4567-e89b-12d3-a456-426614174000";
const insight = { text: "Response-specific behavior <script>alert(1)</script>", evidence: ["trades"] };
const data = {
  backtest_id: id, mode: "paper", status: "available", unavailable_reason: null,
  provider: "anthropic", model: "configured-model", generated_at: "2026-11-07T12:00:00Z",
  facts: [{ id: "trades", label: "Trades", value: "7" }], disclaimer: "Response-specific disclaimer.",
  interpretation: { summary: "Response-specific summary.", strategy_behavior: [insight], strengths: [{ ...insight, text: "Response-specific strength." }], weaknesses: [], risk_factors: [{ ...insight, text: "Response-specific risk." }], limitations: [{ ...insight, text: "Response-specific limitation." }] },
};
const ui = Object.fromEntries(["Badge", "Button", "Panel"].map((name) => [name, function Mock() {}]));
function text(element) {
  if (Array.isArray(element)) return element.map(text).join("");
  if (element === null || element === undefined || typeof element === "boolean") return "";
  return typeof element === "object" ? text(element.props?.children) : String(element);
}
async function panel(state, load = async () => {}) {
  const component = await mount("../src/components/backtest-insights.tsx", {
    "../hooks/use-backtest-analysis": { useBacktestAnalysis: () => ({ state, load }) }, "./ui": ui,
  }, "BacktestInsights", { backtestId: id });
  return component.render();
}

test("insights are requested explicitly; loading disables repeat requests", async () => {
  const calls = [];
  const idle = await panel({ status: "idle" }, async (id) => calls.push(id));
  assert.equal(calls.length, 0);
  assert.match(text(idle), /No insights have been generated/);
  nodes(idle).find((node) => node.type === ui.Button).props.onClick();
  assert.deepEqual(calls, [id]);
  const loading = await panel({ status: "loading", backtestId: id });
  assert.equal(loading.props["aria-busy"], true);
  assert.ok(nodes(loading).some((node) => node.props?.role === "status"));
  assert.equal(nodes(loading).find((node) => node.type === ui.Button).props.disabled, true);
  assert.doesNotMatch(text(loading), /Response-specific summary/);
});
