import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { apiOrigin } from "../src/lib/api-origin.ts";
import nextConfig from "../next.config.ts";
import { PHASE_PRODUCTION_BUILD, PHASE_DEVELOPMENT_SERVER } from "next/constants.js";
import { getHealth } from "../src/lib/api.ts";

const originalOrigin = process.env.NEXT_PUBLIC_API_ORIGIN;
const originalMode = process.env.NODE_ENV;
afterEach(() => {
  for (const [key, value] of [["NEXT_PUBLIC_API_ORIGIN", originalOrigin], ["NODE_ENV", originalMode]]) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

test("deployment requires an explicit HTTPS backend origin while development stays local", () => {
  assert.equal(apiOrigin(undefined, false), "http://localhost:8000");
  assert.equal(apiOrigin("http://127.0.0.1:8100", false), "http://127.0.0.1:8100");
  assert.equal(apiOrigin("https://vektor-backend.fly.dev/", true), "https://vektor-backend.fly.dev");
  for (const value of [undefined, "", " ", "http://backend.example.com", "https://localhost", "https://127.0.0.1", "https://[::1]", "https://0.0.0.0", "https://test.localhost", "https://backend.example.com/api/v1", "https://backend.example.com?key=private", "https://backend.example.com#fragment", "https://user:private@backend.example.com", "file:///tmp/data"]) {
    assert.throws(() => apiOrigin(value, true), (error) => /NEXT_PUBLIC_API_ORIGIN/.test(error.message) && !error.message.includes("private"));
  }
});

test("Next production config fails before building without a valid origin; development needs none", () => {
  process.env.NEXT_PUBLIC_API_ORIGIN = "";
  assert.deepEqual(nextConfig(PHASE_DEVELOPMENT_SERVER), {});
  assert.throws(() => nextConfig(PHASE_PRODUCTION_BUILD), /NEXT_PUBLIC_API_ORIGIN/);
  process.env.NEXT_PUBLIC_API_ORIGIN = "https://vektor-backend.fly.dev";
  assert.deepEqual(nextConfig(PHASE_PRODUCTION_BUILD), {});
});

test("production browser requests reach the configured versioned backend and handle downtime safely", async (t) => {
  process.env.NODE_ENV = "production";
  process.env.NEXT_PUBLIC_API_ORIGIN = "https://vektor-backend.fly.dev";
  const request = t.mock.method(globalThis, "fetch", async (url) => {
    assert.equal(url.href, "https://vektor-backend.fly.dev/api/v1/health");
    return Response.json({ status: "ok", app: "Vektor", version: "0.1.0", environment: "production", trading_mode: "paper" });
  });
  assert.equal((await getHealth()).trading_mode, "paper");
  request.mock.mockImplementation(async () => { throw new Error("private host failure"); });
  await assert.rejects(getHealth(), /could not be reached/);
});
