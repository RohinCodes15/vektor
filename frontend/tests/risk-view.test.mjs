import { test } from "node:test";
import assert from "node:assert/strict";
import { mount } from "./component-runtime.mjs";
import { unavailableRisk } from "./allocation-fixtures.mjs";

test("risk view reports the backend unavailable reason and window assumptions", async () => {
  const app = await mount("../src/components/portfolio-risk.tsx", { "./ui": { Badge: "badge", Panel: "panel" } }, "PortfolioRiskView", { risk: unavailableRisk });
  const result = JSON.stringify(app.render(), (_key, value) => typeof value === "function" ? undefined : value);
  assert.match(result, /Insufficient aligned history/); assert.match(result, /not realized portfolio performance/);
  assert.doesNotMatch(result, /7.0000%/);
});
