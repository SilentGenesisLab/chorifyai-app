import Redis from "ioredis";

// Singleton across hot-reloads. Node runtime only (never import in middleware).
const g = globalThis as unknown as { __redis?: Redis };

export const redis =
  g.__redis ??
  new Redis(process.env.REDIS_URL ?? "redis://localhost:6379", {
    maxRetriesPerRequest: 3,
  });

if (process.env.NODE_ENV !== "production") g.__redis = redis;
