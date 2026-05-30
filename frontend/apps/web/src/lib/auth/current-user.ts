import { prisma } from "@/lib/db";
import { getSession } from "@/lib/auth/session";

/** Resolve the logged-in user + their active organization, or null. */
export async function getCurrentUser() {
  const session = await getSession();
  if (!session) return null;

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    include: { memberships: { include: { org: true } } },
  });
  if (!user) return null;

  const currentOrg =
    user.memberships.find((m) => m.orgId === session.orgId)?.org ??
    user.memberships[0]?.org ??
    null;

  return { user, currentOrg, session };
}

export type CurrentUser = NonNullable<Awaited<ReturnType<typeof getCurrentUser>>>;
