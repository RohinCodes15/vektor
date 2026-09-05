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

test("insights render actual response text, evidence, empty categories, and disclaimer safely", async () => {
  const tree = await panel({ status: "success", data });
  const content = text(tree);
  for (const expected of [data.interpretation.summary, insight.text, "Response-specific strength.", "Response-specific risk.", "Response-specific limitation.", "Trades: 7", data.disclaimer, "None returned by the provider."]) assert.ok(content.includes(expected), expected);
  assert.deepEqual(nodes(tree).filter((node) => node.type === "h4").map(text), ["Strategy summary", "Strategy behavior", "Strengths", "Weaknesses", "Risks", "Limitations"]);
  assert.ok(!nodes(tree).some((node) => node.type === "script" || node.props?.dangerouslySetInnerHTML));
  assert.equal(nodes(tree).find((node) => node.type === ui.Button).props.children, "Regenerate AI insights");
});

test("unavailable and error states offer retry without fabricated interpretations", async () => {
  const unavailable = await panel({ status: "unavailable", data: { ...data, status: "unavailable", unavailable_reason: "No provider configured.", interpretation: null, provider: null, model: null } });
  assert.match(text(unavailable), /No provider configured/);
  assert.ok(nodes(unavailable).some((node) => node.type === "details"));
  const error = await panel({ status: "error", backtestId: id, message: "The AI provider is unavailable." });
  assert.equal(nodes(error).find((node) => node.props?.role === "alert").props.children, "The AI provider is unavailable.");
  for (const tree of [unavailable, error]) {
    assert.doesNotMatch(text(tree), /Response-specific summary|Strategy summary/);
    assert.equal(nodes(tree).find((node) => node.type === ui.Button).props.children, "Try again");
  }
});
