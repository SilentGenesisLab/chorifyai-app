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
    // Only mark Secure when actually served over HTTPS. Default OFF so the
    // persistent cookie works over http://localhost / LAN in local production
    // (`next start`) — otherwise the browser drops it and you re-login each time.
    // Set SESSION_COOKIE_SECURE=true when deploying behind HTTPS.
    secure: process.env.SESSION_COOKIE_SECURE === "true",
    path: "/",
    maxAge: sessionTtlSeconds(), // persistent (30d) → survives browser restart
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
