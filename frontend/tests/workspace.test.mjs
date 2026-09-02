import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// Inspect the production-rendered page from the build without requiring a listening server.
test("workspace renders accessible primitives and honest paper-only boundaries", { timeout: 30000 }, async () => {
  const html = await readFile(".next/server/app/index.html", "utf8");
    assert.match(html, /lang="en"/);
    assert.match(html, /Skip to content/);
    for (const id of ["main", "overview", "backtest", "market", "activity"]) {
      assert.ok(html.includes(`id="${id}"`));
      assert.ok(html.includes(`href="#${id}"`));
    }
    assert.match(html, /PAPER ONLY/);
    assert.match(html, /id="backend-status"/);
    assert.match(html, /Checking the paper-only health endpoint/);
    assert.match(html, /aria-busy="true"/);
    assert.match(html, /aria-live="polite"/);
    assert.doesNotMatch(html, />Connected</);
    assert.match(html, /<main id="main" tabindex="-1">/);
    assert.match(html, /NO LIVE DATA/);
    assert.match(html, /Loading paper portfolios/);
    assert.match(html, /Historical daily closes load on demand/);
    assert.match(html, /label for="history-start-AAPL"/);
    assert.match(html, /label for="history-end-AAPL"/);
    assert.match(html, /No live quotes/);
    assert.match(html, /aria-label="History time range"/);
    for (const range of ["1M", "3M", "6M", "1Y", "ALL"]) assert.ok(html.includes(`>${range}</button>`));
    assert.match(html, /aria-pressed="true">1Y/);
    assert.ok(html.includes('>Search</button>'));
    assert.match(html, /href="#backtest"[^>]*>New simulation<\/a>/);
    assert.match(html, /<label for="backtest-symbol">Ticker<\/label>/);
    assert.match(html, /Buy &amp; Hold/);
    assert.match(html, /SMA Crossover/);
    assert.ok(html.indexOf('href="#activity"') < html.indexOf('href="#backtest"'));
    assert.match(html, /03 \/ EXPLORE/);
    assert.match(html, /<label for="symbol-search">Find a symbol<\/label>/);
    assert.match(html, /aria-describedby="symbol-search-hint"/);
    assert.match(html, /id="symbol-search-hint"/);
    assert.match(html, /aria-label="Open navigation" aria-expanded="false"/);
    assert.match(html, /aria-label="Collapse sidebar" aria-expanded="true"/);
    const css = await readFile("src/app/globals.css", "utf8");
    assert.match(css, /prefers-reduced-motion: reduce/);
    assert.match(css, /:focus-visible/);

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
