import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { risk } from "./allocation-fixtures.mjs";
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);
const imports = { "./ui": { Badge: "badge", Panel: "panel" } };

test("correlation heatmap mirrors only reported pairs; missing diagonal is unavailable", async () => {
  const app = await mount("../src/components/portfolio-risk.tsx", imports, "CorrelationHeatmap", { risk });
  let tree = app.render(); const cells = nodes(tree).filter((node) => node.type === "td");
  assert.equal(cells.length, 4); assert.deepEqual(cells.map((node) => node.props.children), ["Unavailable", "-0.2000", "-0.2000", "Unavailable"]);
  cells[1].props.onFocus(); tree = app.render(); assert.match(nodes(tree).find((node) => node.props?.role === "status").props.children, /AAPL \/ MSFT: -0.2000/);
});

test("constant series never receive inferred correlations", async () => {
  const constant = { ...risk, correlations: [{ symbol_a: "AAPL", symbol_b: "MSFT", correlation: null }] };
  const app = await mount("../src/components/portfolio-risk.tsx", imports, "CorrelationHeatmap", { risk: constant });
  assert.ok(nodes(app.render()).filter((node) => node.type === "td").every((node) => node.props.children === "Unavailable"));
  assert.match(text(app.render()), /Unavailable/);
});
