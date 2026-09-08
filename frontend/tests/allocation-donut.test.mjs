import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { formatMoney } from "../src/lib/portfolio-values.ts";
import { allocation, cashOnly, unpriced } from "./allocation-fixtures.mjs";

const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);

test("allocation donut includes cash and exact weights, with keyboard and legend exploration", async () => {
  const app = await mount("../src/components/allocation-donut.tsx", { "../lib/portfolio-values": { formatMoney } }, "AllocationDonut", { allocation });
  let tree = app.render(); assert.match(text(tree), /Cash/); assert.match(text(tree), /40.0000%/);
  const segment = nodes(tree).find((node) => node.type === "circle" && node.props["aria-label"].startsWith("MSFT"));
  assert.equal(segment.props.tabIndex, 0);
  segment.props.onKeyDown({ key: "Enter", preventDefault() {} }); tree = app.render();
  assert.match(nodes(tree).find((node) => node.props?.role === "status").props.children.join(""), /MSFT.*20.0000%.*\$200.00/);
  nodes(tree).find((node) => node.type === "button").props.onClick(); tree = app.render();
  assert.match(nodes(tree).find((node) => node.props?.role === "status").props.children.join(""), /Cash.*\$400.00/);
  app.unmount();
});

test("cash-only donut works and unknown or zero weights never draw invented allocations", async () => {
  for (const data of [cashOnly, unpriced, { ...cashOnly, equity: "0.00", cash_weight_pct: null }]) {
    const app = await mount("../src/components/allocation-donut.tsx", { "../lib/portfolio-values": { formatMoney } }, "AllocationDonut", { allocation: data });
    const tree = app.render();
    if (data === cashOnly) assert.match(text(tree), /100.0000%/);
    else { assert.match(text(tree), /Allocation chart unavailable/); assert.equal(nodes(tree).some((node) => node.type === "svg"), false); }
  }
});
