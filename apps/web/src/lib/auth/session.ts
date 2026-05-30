// Node-side session helpers (read/write the httpOnly cookie).
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/constants";
import {
  signSession,
  verifySession,
  sessionTtlSeconds,
  type SessionPayload,
} from "@/lib/auth/jwt";

export async function setSessionCookie(payload: {
  userId: string;
  phone: string;
  orgId: string;
}): Promise<void> {
  const token = await signSession(payload);
  const jar = await cookies();
  jar.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: sessionTtlSeconds(),
  });
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
}

export async function getSession(): Promise<SessionPayload | null> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  return verifySession(token);
}
