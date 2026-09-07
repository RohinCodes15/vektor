import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { risk } from "./allocation-fixtures.mjs";
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);
const imports = { "./ui": { Badge: "badge", Panel: "panel" } };

test("risk chart shows signed backend contributions without clamping hedge shares", async () => {
  const app = await mount("../src/components/portfolio-risk.tsx", imports, "RiskContribution", { risk });
  let tree = app.render(); assert.match(text(tree), /-14.2857%/);
  const bars = nodes(tree).filter((node) => node.type === "rect");
  assert.ok(bars.some((node) => node.props.x < 330)); assert.ok(bars.some((node) => node.props.x === 330));
  nodes(tree).find((node) => node.type === "g" && node.props["aria-label"].startsWith("MSFT")).props.onFocus(); tree = app.render();
  assert.match(nodes(tree).find((node) => node.props?.role === "status").props.children, /MSFT.*-1.0000.*-14.2857%/);
});

test("zero volatility leaves contributions undefined", async () => {
  const zero = { ...risk, portfolio_volatility_pct: "0.0000", assets: risk.assets.map((asset) => ({ ...asset, volatility_contribution_pct: null, contribution_share_pct: null })) };
  const app = await mount("../src/components/portfolio-risk.tsx", imports, "RiskContribution", { risk: zero });
  assert.match(text(app.render()), /Risk contributions unavailable/);
  assert.equal(nodes(app.render()).some((node) => node.type === "svg"), false);
});
