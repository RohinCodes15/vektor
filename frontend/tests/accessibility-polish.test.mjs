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

