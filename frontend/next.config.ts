import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

// `page.dev.tsx` routes (the design system showcase) exist only on `next dev`: a production
// build doesn't recognize them as pages, so they never reach the bundle.
const DEFAULT_PAGE_EXTENSIONS = ["tsx", "ts", "jsx", "js"];

export default function config(phase: string): NextConfig {
  return phase === PHASE_DEVELOPMENT_SERVER
    ? { ...nextConfig, pageExtensions: ["dev.tsx", ...DEFAULT_PAGE_EXTENSIONS] }
    : nextConfig;
}
