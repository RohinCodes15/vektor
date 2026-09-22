import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { getHealth } from "../src/lib/api.ts";

const originalOrigin = process.env.NEXT_PUBLIC_API_ORIGIN;
const health = { status: "ok", app: "Vektor", version: "0.1.0", environment: "development", trading_mode: "paper" };
afterEach(() => {
  if (originalOrigin === undefined) delete process.env.NEXT_PUBLIC_API_ORIGIN;
  else process.env.NEXT_PUBLIC_API_ORIGIN = originalOrigin;
});

test("health uses the versioned endpoint, no cache, and no credentials", async (t) => {
  delete process.env.NEXT_PUBLIC_API_ORIGIN;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.href, "http://localhost:8000/api/v1/health");
    assert.equal(options.method, "GET");
    assert.equal(options.cache, "no-store");
    assert.equal(options.credentials, "omit");
    assert.equal(options.redirect, "error");
    assert.ok(options.signal instanceof AbortSignal);
    return Response.json(health);
  });
  assert.deepEqual(await getHealth(), health);
});

test("health supports a configured backend origin", async (t) => {
  process.env.NEXT_PUBLIC_API_ORIGIN = "http://127.0.0.1:8100";
  t.mock.method(globalThis, "fetch", async (url) => {
    assert.equal(url.href, "http://127.0.0.1:8100/api/v1/health");
    return Response.json(health);
  });
  assert.deepEqual(await getHealth(), health);
});

test("invalid origins fail before any request", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const origin of ["invalid", "file:///tmp/data", "https://user:secret@localhost", "http://localhost:8000/api", "http://localhost:8000?token=secret"]) {
    process.env.NEXT_PUBLIC_API_ORIGIN = origin;
    await assert.rejects(getHealth(), /Backend address is invalid/);
  }
  assert.equal(request.mock.callCount(), 0);
});
