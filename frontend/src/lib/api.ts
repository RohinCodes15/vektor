/** Mirrors backend/app/contracts.py HealthResponse; no contract changes. */
export type HealthResponse = Readonly<{
  status: "ok";
  app: string;
  version: string;
  environment: string;
  trading_mode: "paper";
}>;

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const keys = ["status", "app", "version", "environment", "trading_mode"];
  return Object.keys(record).length === keys.length
    && keys.every((key) => Object.hasOwn(record, key))
    && record.status === "ok"
    && record.trading_mode === "paper"
    && typeof record.app === "string"
    && typeof record.version === "string"
    && typeof record.environment === "string";
}

async function requestJson(path: string, name: "health" | "market history", signal?: AbortSignal, params?: URLSearchParams): Promise<unknown> {
  const operation = name === "health" ? "health check" : "market history request";
  let url: URL;
  try {
    url = new URL(process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000");
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error();
    url.pathname = path;
    if (params) url.search = params.toString();
  } catch {
    throw new Error("Backend address is invalid. Check NEXT_PUBLIC_API_ORIGIN.");
  }

  const timeout = AbortSignal.timeout(5000);
  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error(`Backend ${operation} timed out. Try again.`);
    throw new Error("Backend could not be reached. Check that it is running and allows this frontend origin.");
  }
  if (!response.ok) throw new Error(`Backend ${operation} failed (HTTP ${response.status}). Try again.`);

  let data: unknown;
  try {
    data = await response.json();
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error(`Backend ${operation} timed out. Try again.`);
    throw new Error(`Backend returned an invalid ${name} response.`);
  }
  return data;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const data = await requestJson("/api/v1/health", "health", signal);
  if (!isHealthResponse(data)) throw new Error("Backend returned an incompatible health response. Expected a healthy paper-only service.");
  return data;
}
