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
async function demo() {
  return mount("../src/components/guided-demo.tsx", { "./ui": ui }, "GuidedDemo");
}

test("demo is opt-in, walks all existing features, and makes no backend or AI requests", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch");
  const component = await demo();
  assert.equal(button(component, "Explore Demo")["aria-expanded"], false);
  assert.equal(nodes(component.render()).some((node) => node.props?.id === "demo-steps"), false);
  button(component, "Explore Demo").onClick();
  assert.equal(button(component, "Back").disabled, true);
  const targets = ["market", "activity", "backtest", "backtest", "comparison", "optimization"];
  const content = [];
  for (let index = 0; index < targets.length; index++) {
    const tree = component.render();
    content.push(text(tree));
    assert.equal(nodes(tree).find((node) => node.type === "a" && node.props.className === "button button-primary").props.href, `#${targets[index]}`);
    assert.match(text(tree), new RegExp(`Step ${index + 1} of 6`));
    if (index < targets.length - 1) button(component, "Next").onClick();
  }
  assert.match(content[0], /Yahoo Finance.*historical, not live quotes/);
  assert.match(content[1], /simulated balances, not real funds/);
  assert.match(content[3], /off by default, and paid when enabled/);
  assert.match(content[3], /After a successful backtest/);
  button(component, "Back").onClick();
  assert.match(text(component.render()), /Compare strategy configurations/);
  button(component, "Next").onClick();
  button(component, "Finish demo").onClick();
  assert.equal(button(component, "Explore Demo")["aria-expanded"], false);
  assert.equal(fetch.mock.callCount(), 0);
});

test("demo focuses step headings, returns focus on exit, and supports Escape and restart", async () => {
  const component = await demo();
  let returned = 0, headingFocus = 0;
  button(component, "Explore Demo").ref.current = { focus: () => returned++ };
  component.flush();
  button(component, "Explore Demo").onClick();
  let tree = component.render();
  const heading = nodes(tree).find((node) => node.props?.id === "demo-step-title");
  assert.equal(heading.props.tabIndex, -1);
  heading.props.ref.current = { focus: () => headingFocus++ };
  component.flush();
  assert.equal(headingFocus, 1);
  button(component, "Next").onClick(); component.render(); component.flush();
  assert.equal(headingFocus, 2);
  button(component, "Restart demo").onClick();
  assert.match(text(component.render()), /Step 1 of 6/);
  let stopped = false;
  component.render().props.onKeyDown({ key: "Escape", stopPropagation: () => { stopped = true; } });
  assert.equal(stopped, true);
  assert.equal(returned, 1);
  button(component, "Explore Demo").onClick();
  button(component, "Skip demo").onClick();
  assert.equal(returned, 2);
});

test("feature links move focus and missing sections do not trap the guide", async (t) => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "document");
  let focused = false, missing = false;
  const target = { tabIndex: 0, focus: () => { focused = true; } };
  Object.defineProperty(globalThis, "document", { configurable: true, value: { getElementById: (id) => { assert.equal(id, "market"); return missing ? null : target; } } });
  t.after(() => { if (original) Object.defineProperty(globalThis, "document", original); else delete globalThis.document; });
  const component = await demo(); button(component, "Explore Demo").onClick();
  let link = nodes(component.render()).find((node) => node.type === "a" && node.props.href === "#market");
  link.props.onClick({});
  assert.equal(focused, true); assert.equal(target.tabIndex, -1);
  focused = false; link.props.onClick({ ctrlKey: true }); assert.equal(focused, false);
  missing = true;
  let prevented = false;
  link.props.onClick({ preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.match(nodes(component.render()).find((node) => node.props?.role === "status").props.children, /section is unavailable/);
  button(component, "Next").onClick();
  assert.equal(nodes(component.render()).some((node) => node.props?.role === "status"), false);
  button(component, "Skip demo").onClick();
  assert.equal(button(component, "Explore Demo")["aria-expanded"], false);
});
