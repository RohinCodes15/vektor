import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { once } from "node:events";

// Exercise the production-rendered page rather than duplicating component logic.
test("workspace renders accessible primitives and honest paper-only boundaries", { timeout: 30000 }, async () => {
  const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--port", "0"], { env: { ...process.env, NODE_ENV: "production" } });
  let output = "";
  server.stdout.on("data", (data) => { output += data; });
  server.stderr.on("data", (data) => { output += data; });
  try {
    let response;
    for (let attempt = 0; attempt < 100; attempt++) {
      if (server.exitCode !== null) throw new Error(output);
      const address = output.match(/http:\/\/localhost:(\d+)/);
      if (address) {
        try { response = await fetch(`http://localhost:${address[1]}`); if (response.ok) break; } catch { /* Server may still be starting. */ }
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.ok(response?.ok, output);
    const html = await response.text();
    assert.match(html, /lang="en"/);
    assert.match(html, /Skip to content/);
    for (const id of ["main", "overview", "principles", "components"]) {
      assert.ok(html.includes(`id="${id}"`));
      assert.ok(html.includes(`href="#${id}"`));
    }
    assert.match(html, /Paper only/);
    assert.match(html, /ILLUSTRATIVE RESEARCH PATH/);
    assert.match(html, /Not available/);
    assert.match(html, /<button[^>]*disabled=""[^>]*>Run simulation<\/button>/);
    assert.match(html, /<label for="strategy-name">Strategy name<\/label>/);
    assert.match(html, /aria-describedby="strategy-name-hint"/);
    assert.match(html, /id="strategy-name-hint"/);
    const css = await readFile("src/app/globals.css", "utf8");
    assert.match(css, /prefers-reduced-motion: reduce/);
    assert.match(css, /:focus-visible/);
  } finally {
    if (server.exitCode === null) {
      const exited = once(server, "exit");
      server.kill("SIGTERM");
      await exited;
    }
  }
});

test("theme text and input boundaries meet WCAG contrast thresholds", async () => {
  const css = await readFile("src/app/globals.css", "utf8");
  function luminance(token) {
    const hex = css.match(new RegExp(`--color-${token}: #([a-f0-9]{6})`))?.[1];
    assert.ok(hex, `Missing color token: ${token}`);
    const [r, g, b] = hex.match(/../g).map((channel) => {
      const value = parseInt(channel, 16) / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return r * 0.2126 + g * 0.7152 + b * 0.0722;
  }
  for (const [foreground, background, minimum] of [
    ["ink", "surface", 4.5], ["muted", "surface", 4.5],
    ["teal", "surface", 4.5], ["control", "canvas", 3],
    ["control", "raised", 3],
  ]) {
    const values = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
    assert.ok((values[1] + 0.05) / (values[0] + 0.05) >= minimum, `${foreground} on ${background}`);
  }
});
