import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow a separate build dir (e.g. a parallel preview server on another port)
  // so two `next dev` instances don't fight over .next.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // @chorify/db is published as TypeScript source — let Next transpile it.
  transpilePackages: ["@chorify/db"],
  // Keep Node-only packages out of the bundle.
  serverExternalPackages: [
    "@prisma/client",
    "prisma",
    "ioredis",
    "ali-oss",
    "@alicloud/dysmsapi20170525",
    "@alicloud/openapi-client",
    "@alicloud/tea-util",
  ],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
  // Same-origin proxy to the FastAPI backend (uploads + AI generation).
  // Keeps the browser on one origin (no CORS) and works in prod where Next
  // forwards server-side to 127.0.0.1:8000.
  async rewrites() {
    const base = process.env.AI_SERVICE_URL ?? "http://127.0.0.1:8000";
    return [
      { source: "/api/upload", destination: `${base}/api/upload` },
      { source: "/api/upload/:path*", destination: `${base}/api/upload/:path*` },
      { source: "/api/material/:path*", destination: `${base}/api/material/:path*` },
      { source: "/api/voice/:path*", destination: `${base}/api/voice/:path*` },
      { source: "/api/split", destination: `${base}/api/split` },
      { source: "/api/split/:path*", destination: `${base}/api/split/:path*` },
      { source: "/api/mix", destination: `${base}/api/mix` },
      { source: "/api/mix/:path*", destination: `${base}/api/mix/:path*` },
    ];
  },
};

export default nextConfig;
