import { getCurrentUser } from "@/lib/auth/current-user";

/** Resolve {userId, orgId} for an authenticated API request, or null. */
export async function requireOrg() {
  const ctx = await getCurrentUser();
  if (!ctx || !ctx.currentOrg) return null;
  return { userId: ctx.user.id, orgId: ctx.currentOrg.id, nickname: ctx.user.nickname };
}
