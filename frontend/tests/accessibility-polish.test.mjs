import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";

test("shared fields associate hints and validation descriptions without dropping input semantics", async () => {
  const component = await mount("../src/components/ui.tsx", { "motion/react-client": { section: "section" } }, "Field", {
    id: "capital", label: "Starting capital", hint: "Virtual USD only.", "aria-describedby": "capital-error", "aria-invalid": true,
    type: "number", required: true, min: "0.01", step: "0.01", value: "10000.00", disabled: true,
  });
  let tree = component.render();
  assert.equal(nodes(tree).find((node) => node.type === "label").props.htmlFor, "capital");
  const input = nodes(tree).find((node) => node.type === "input");
  assert.equal(input.props["aria-describedby"], "capital-error capital-hint");
  assert.equal(input.props["aria-invalid"], true);
  assert.equal(input.props.disabled, true);
  assert.equal(input.props.required, true);
  assert.equal(input.props.value, "10000.00");
  assert.equal(nodes(tree).find((node) => node.props?.id === "capital-hint").props.children, "Virtual USD only.");
  tree = component.render({ id: "ticker", label: "Ticker" });
  assert.equal(nodes(tree).find((node) => node.type === "input").props["aria-describedby"], undefined);
});

test("shared buttons preserve explicit form types, accessible names, and disabled behavior", async () => {
  const component = await mount("../src/components/ui.tsx", { "motion/react-client": { section: "section" } }, "Button", {
    type: "submit", disabled: true, "aria-label": "Run paper strategy comparison", children: "Compare", variant: "secondary",
  });
  const tree = component.render();
  assert.equal(tree.type, "button");
  assert.equal(tree.props.type, "submit");
  assert.equal(tree.props.disabled, true);
  assert.equal(tree.props["aria-label"], "Run paper strategy comparison");
  assert.match(tree.props.className, /button-secondary/);
});

test("navigation reaches all research views and moves keyboard focus to the selected section", async (t) => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "document");
  let focused, toggleFocused = false;
  const targets = Object.fromEntries(["overview", "activity", "backtest", "comparison", "optimization", "market"].map((id) => [id, { tabIndex: 0, focus: (options) => { focused = { id, options }; } }]));
  Object.defineProperty(globalThis, "document", { configurable: true, value: { getElementById: (id) => targets[id] } });
  t.after(() => { if (original) Object.defineProperty(globalThis, "document", original); else delete globalThis.document; });
  const component = await mount("../src/components/dashboard-shell.tsx", {
    "motion/react": { MotionConfig: "MotionConfig", motion: { a: "a", div: "div" }, useReducedMotion: () => true },
    "./health-status": { HealthStatus: function MockHealth() {} }, "./ui": { Badge: function MockBadge() {} },
  }, "DashboardShell", { children: "Dashboard content" });
  let tree = component.render();
  const links = nodes(tree).filter((node) => node.type === "a" && node.props?.className?.startsWith("nav-link"));
  assert.deepEqual(links.map((node) => node.props.href), Object.keys(targets).map((id) => `#${id}`));
  assert.equal(links[0].props["aria-current"], "location");
  for (const link of links) assert.ok(link.props["aria-label"]);
  const toggle = nodes(tree).find((node) => node.props?.className === "icon-button mobile-toggle");
  toggle.props.ref.current = { focus: () => { toggleFocused = true; } };
  toggle.props.onClick();
  tree = component.render();
  assert.equal(nodes(tree).find((node) => node.props?.className === "icon-button mobile-toggle").props["aria-expanded"], true);
  nodes(tree).find((node) => node.props?.href === "#optimization").props.onClick({});
  assert.deepEqual(focused, { id: "optimization", options: { preventScroll: true } });
  assert.equal(targets.optimization.tabIndex, -1);
  assert.equal(toggleFocused, false);
  tree = component.render();
  const closedToggle = nodes(tree).find((node) => node.props?.className === "icon-button mobile-toggle");
  assert.equal(closedToggle.props["aria-expanded"], false);
  closedToggle.props.onClick();
  nodes(component.render()).find((node) => node.type === "aside").props.onKeyDown({ key: "Escape" });
  assert.equal(toggleFocused, true);
  focused = null;
  nodes(component.render()).find((node) => node.props?.href === "#comparison").props.onClick({ metaKey: true });
  assert.equal(focused, null);
});
