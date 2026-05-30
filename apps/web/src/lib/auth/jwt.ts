// Edge-safe session signing/verifying (jose). Used by middleware AND
// route handlers, so it must NOT import next/headers or any Node-only API.
import { SignJWT, jwtVerify, type JWTPayload } from "jose";

export interface SessionPayload extends JWTPayload {
  userId: string;
  phone: string;
  orgId: string;
}

function getSecret(): Uint8Array {
  const s = process.env.JWT_SECRET;
  if (!s || s.length < 16) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("JWT_SECRET is required (min 16 chars) in production");
    }
    // dev fallback so the app boots without configuration
    return new TextEncoder().encode("dev-insecure-secret-change-me-please-0001");
  }
  return new TextEncoder().encode(s);
}

function ttlDays(): number {
  const n = Number(process.env.SESSION_TTL_DAYS ?? "30");
  return Number.isFinite(n) && n > 0 ? n : 30;
}

export function sessionTtlSeconds(): number {
  return ttlDays() * 24 * 60 * 60;
}

export async function signSession(payload: {
  userId: string;
  phone: string;
  orgId: string;
}): Promise<string> {
  return new SignJWT({ ...payload })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${ttlDays()}d`)
    .sign(getSecret());
}

export async function verifySession(
  token: string | undefined | null,
): Promise<SessionPayload | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, getSecret());
    if (
      typeof payload.userId === "string" &&
      typeof payload.phone === "string" &&
      typeof payload.orgId === "string"
    ) {
      return payload as SessionPayload;
    }
    return null;
  } catch {
    return null;
  }
}
