import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { id, other, allocation, risk } from "./allocation-fixtures.mjs";

const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);
async function section(api) {
  return mount("../src/components/portfolio-allocation.tsx", {
    "../lib/api": api, "./allocation-summary": { AllocationSummary: "allocation" }, "./portfolio-risk": { PortfolioRiskView: "risk" },
    "./ui": { Badge: "badge", Button: "button", Panel: "panel" },
  }, "PortfolioAllocationSection", { id });
}

test("allocation and risk fail independently, support retry and refresh on portfolio revisions", async () => {
  let fail = true; let count = 0;
  const app = await section({ getPortfolioAllocation: async () => { count++; return allocation; }, getPortfolioRisk: async () => { if (fail) throw new Error("Provider unavailable"); return risk; } });
  let tree = app.render(); assert.match(text(tree), /Loading portfolio allocation/); assert.match(text(tree), /Loading portfolio risk/);
  app.flush(); await settle(); tree = app.render();
  assert.ok(nodes(tree).some((node) => node.type === "allocation")); assert.match(text(tree), /Provider unavailable/);
  fail = false; nodes(tree).find((node) => node.type === "button" && node.props.children === "Retry risk").props.onClick();
  tree = app.render(); assert.equal(nodes(tree).some((node) => node.type === "allocation"), false);
  app.flush(); await settle(); tree = app.render(); assert.ok(nodes(tree).some((node) => node.type === "risk"));
  app.render({ id, refreshVersion: 1 }); app.flush(); await settle(); assert.equal(count, 3);
  app.unmount();
});

test("portfolio switches hide stale responses immediately and cancel both pending requests", async () => {
  const requests = [];
  const app = await section({ getPortfolioAllocation: (id, signal) => new Promise((resolve) => requests.push({ id, signal, resolve })), getPortfolioRisk: (id, signal) => new Promise((resolve) => requests.push({ id, signal, resolve })) });
  app.render(); app.flush(); await settle();
  const next = app.render({ id: other }); assert.equal(nodes(next).some((node) => node.type === "allocation"), false);
  app.flush(); await settle(); assert.equal(requests[0].signal.aborted, true); assert.equal(requests[1].signal.aborted, true);
  requests[2].resolve({ ...allocation, portfolio_id: other }); requests[3].resolve({ ...risk, portfolio_id: other }); await settle();
  requests[0].resolve(allocation); requests[1].resolve(risk); await settle();
  const tree = app.render({ id: other }); assert.equal(nodes(tree).find((node) => node.type === "allocation").props.allocation.portfolio_id, other);
  app.unmount(); assert.equal(requests.at(-1).signal.aborted, true);
});

test("new paper trades advance the allocation and risk refresh version", async () => {
  const app = await mount("../src/components/portfolio-dashboard.tsx", {
    "../lib/api": {}, "../lib/portfolio-values": {},
    "./allocation-summary": {},
    "./portfolio-allocation": { PortfolioAllocationSection: "allocation" },
    "./portfolio-performance": { PortfolioPerformance: "performance" },
    "./transaction-history": { TransactionHistory: "transactions" },
    "./ui": { Badge: "badge", Button: "button", MetricCard: "metric", Panel: "panel" },
  }, "PortfolioDetails", { id });
  let tree = app.render();
  assert.equal(nodes(tree).find((node) => node.type === "allocation").props.refreshVersion, 0);
  nodes(tree).find((node) => node.type === "transactions").props.onTrades(); tree = app.render();
  assert.equal(nodes(tree).find((node) => node.type === "allocation").props.refreshVersion, 1);
});
