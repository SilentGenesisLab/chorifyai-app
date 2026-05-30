import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
};

export default nextConfig;
