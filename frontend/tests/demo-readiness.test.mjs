import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";

const ui = Object.fromEntries(["Badge", "Button", "Panel"].map((name) => [name, function Mock() {}]));
function text(element) {
  if (Array.isArray(element)) return element.map(text).join("");
  if (element === null || element === undefined || typeof element === "boolean") return "";
  return typeof element === "object" ? text(element.props?.children) : String(element);
}
function button(component, label) {
  const node = nodes(component.render()).find((node) => node.type === ui.Button && node.props.children === label);
  assert.ok(node, label); return node.props;
}
async function demo() { return mount("../src/components/guided-demo.tsx", { "./ui": ui }, "GuidedDemo"); }

test("landing puts a single optional guide below the headline and preserves all workflows", async () => {
  const names = { "dashboard-shell": "DashboardShell", "market-workspace": "MarketWorkspace", reveal: "Reveal", "portfolio-dashboard": "PortfolioDashboard", "backtest-form": "BacktestForm", "comparison-form": "ComparisonForm", "optimization-form": "OptimizationForm", "guided-demo": "GuidedDemo" };
  const imports = Object.fromEntries(Object.entries(names).map(([file, name]) => [`@/components/${file}`, { [name]: function Mock() {} }]));
  imports["@/components/ui"] = ui;
  const component = await mount("../src/app/page.tsx", imports, "default");
  const tree = component.render(), elements = nodes(tree), guide = imports["@/components/guided-demo"].GuidedDemo;
  assert.equal(elements.filter((node) => node.type === "h1").length, 1);
  assert.match(text(elements.find((node) => node.type === "h1")), /Research strategies.Keep capital simulated/);
  assert.match(text(tree), /real historical prices/);
  assert.match(text(tree), /No live quotes or real-money execution/);
  assert.equal(elements.filter((node) => node.type === guide).length, 1);
  assert.ok(elements.findIndex((node) => node.type === "h1") < elements.findIndex((node) => node.type === guide));
  for (const file of ["backtest-form", "comparison-form", "optimization-form", "market-workspace"]) assert.ok(elements.some((node) => node.type === Object.values(imports[`@/components/${file}`])[0]));
});

test("guide has working Next/Back/Finish links with no requests, fabricated results, or dangling controls", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch");
  const component = await demo();
  assert.equal(button(component, "Explore Demo")["aria-controls"], undefined);
  button(component, "Explore Demo").onClick();
  assert.equal(button(component, "Restart demo")["aria-controls"], "demo-steps");
  assert.equal(button(component, "Back").disabled, true);
  const content = [];
  for (const [index, target] of ["market", "activity", "backtest", "backtest", "comparison", "optimization"].entries()) {
    const tree = component.render(); content.push(text(tree));
    assert.match(text(tree), new RegExp(`Step ${index + 1} of 6`));
    assert.equal(nodes(tree).find((node) => node.type === "a" && node.props.className === "button button-primary").props.href, `#${target}`);
    if (index < 5) button(component, "Next").onClick();
  }
  assert.match(content[0], /historical, not live quotes/);
  assert.match(content[1], /simulated balances, not real funds/);
  assert.match(content[3], /off by default, and paid when enabled/);
  assert.match(content[3], /After a successful backtest/);
  button(component, "Back").onClick(); assert.match(text(component.render()), /Compare strategy configurations/);
  button(component, "Next").onClick(); button(component, "Finish demo").onClick();
  assert.equal(button(component, "Explore Demo")["aria-expanded"], false);
  assert.equal(fetch.mock.callCount(), 0);
});
