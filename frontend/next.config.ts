import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants.js";
import { apiOrigin } from "./src/lib/api-origin.ts";

export default function nextConfig(phase: string): NextConfig {
  if (phase === PHASE_PRODUCTION_BUILD) apiOrigin(process.env.NEXT_PUBLIC_API_ORIGIN, true);
  return {};
}
