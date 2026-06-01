/**
 * Seed the bare minimum so SMS login works: the demo organization + an owner
 * membership. Freshly-logged-in users join DEMO_ORG so they share one workspace.
 *
 * NO mock content — projects / distributions / cloud-drive are all REAL data
 * created by users. (Re-running seed is safe: it never wipes real data.)
 */
import { PrismaClient, Role, Plan } from "@prisma/client";

const prisma = new PrismaClient();

export const DEMO_ORG_ID = "org_demo";
const DEMO_USER_ID = "user_demo";

async function main() {
  const org = await prisma.organization.upsert({
    where: { id: DEMO_ORG_ID },
    update: {},
    create: {
      id: DEMO_ORG_ID,
      name: "尊爱日用 · 广州",
      plan: Plan.ENTERPRISE,
    },
  });

  const user = await prisma.user.upsert({
    where: { id: DEMO_USER_ID },
    update: {},
    create: { id: DEMO_USER_ID, phone: "13800000000", nickname: "管理员" },
  });

  await prisma.membership.upsert({
    where: { userId_orgId: { userId: user.id, orgId: org.id } },
    update: {},
    create: { userId: user.id, orgId: org.id, role: Role.OWNER },
  });

  console.log(`Seeded org=${org.name} (+owner). No mock data — real content only.`);
}

main()
  .then(async () => {
    await prisma.$disconnect();
  })
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });
