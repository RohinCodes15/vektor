import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { formatMoney } from "../src/lib/portfolio-values.ts";
import { allocation } from "./allocation-fixtures.mjs";
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);

test("position table distinguishes equity and invested weights and reports concentration from API", async () => {
  const app = await mount("../src/components/allocation-summary.tsx", {
    "../lib/portfolio-values": { formatMoney }, "./allocation-donut": { AllocationDonut: "donut" },
    "./ui": { Badge: "badge", MetricCard: "metric", Panel: "panel" },
  }, "AllocationSummary", { allocation: { ...allocation, stale_symbols: ["AAPL"], assets: [{ ...allocation.assets[0], stale: true }, allocation.assets[1]] } });
  const tree = app.render();
  const metrics = nodes(tree).filter((node) => node.type === "metric");
  assert.equal(metrics[0].props.value, "66.6667%"); assert.equal(metrics[1].props.value, "0.5556");
  for (const value of ["Cash", "Equity weight", "Position weight", "Stale", "2026-11-05", "$400.00"]) assert.ok(text(tree).includes(value));
  assert.ok(nodes(tree).some((node) => node.props?.role === "region" && node.props.tabIndex === 0));
});
