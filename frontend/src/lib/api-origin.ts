export function apiOrigin(value: string | undefined, production: boolean): string {
  try {
    if (production && !value?.trim()) throw new Error();
    const url = new URL(value || "http://localhost:8000");
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash)
      throw new Error();
    if (production && (url.protocol !== "https:" || ["localhost", "0.0.0.0", "[::1]"].includes(url.hostname)
      || url.hostname.endsWith(".localhost") || url.hostname.startsWith("127."))) throw new Error();
    return url.origin;
  } catch {
    throw new Error(production
      ? "NEXT_PUBLIC_API_ORIGIN must be a public HTTPS backend origin without a path, query, fragment, or credentials. Set it before building production."
      : "Backend address is invalid. Check NEXT_PUBLIC_API_ORIGIN.");
  }
}
