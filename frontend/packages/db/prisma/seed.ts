/**
 * Seed demo data that mirrors the Kuaizi screenshots:
 * one organization + owner, recent projects, and TikTok distributions.
 * Idempotent (upsert by fixed id). The cloud drive is intentionally NOT seeded
 * — it holds only real OSS uploads and is reset to empty on each seed.
 *
 * The demo org id is referenced by the login flow so freshly-logged-in
 * users join it and immediately see realistic data.
 */
import {
  PrismaClient,
  ProjectType,
  ProjectStatus,
  Platform,
  Role,
  Plan,
} from "@prisma/client";

const prisma = new PrismaClient();

export const DEMO_ORG_ID = "org_demo";
const DEMO_USER_ID = "user_demo";

const d = (s: string) => new Date(s);

async function main() {
  const org = await prisma.organization.upsert({
    where: { id: DEMO_ORG_ID },
    update: {},
    create: {
      id: DEMO_ORG_ID,
      name: "尊爱日用 · 广州",
      description: "演示组织",
      plan: Plan.ENTERPRISE,
    },
  });

  const user = await prisma.user.upsert({
    where: { id: DEMO_USER_ID },
    update: {},
    create: {
      id: DEMO_USER_ID,
      phone: "13800000000",
      nickname: "朱佳俊",
    },
  });

  await prisma.membership.upsert({
    where: { userId_orgId: { userId: user.id, orgId: org.id } },
    update: {},
    create: { userId: user.id, orgId: org.id, role: Role.OWNER },
  });

  const base = { orgId: org.id, createdById: user.id };

  // ---- 云盘重置 ----
  // The cloud drive holds ONLY real OSS uploads — no mock files/folders.
  // Wipe any leftover drive rows so a freshly-seeded org starts with an empty drive.
  await prisma.asset.deleteMany({ where: { orgId: org.id } });
  await prisma.folder.deleteMany({ where: { orgId: org.id } });

  // ---- 最近工程 / 合成量产 ----
  const projects = [
    {
      id: "proj_ai",
      name: "AI工程",
      type: ProjectType.SMART_MIX,
      status: ProjectStatus.READY,
      comboCount: 12,
      at: "2026-05-30T19:44:43",
    },
    {
      id: "proj_test1",
      name: "测试1",
      type: ProjectType.SMART_MIX,
      status: ProjectStatus.DRAFT,
      comboCount: 0,
      at: "2026-05-30T10:21:07",
    },
    {
      id: "proj_0420_1757",
      name: "新建视频2026-04-20-17-57",
      type: ProjectType.SMART_MIX,
      status: ProjectStatus.READY,
      comboCount: 5,
      at: "2026-05-29T16:11:43",
    },
    {
      id: "proj_0420_1636",
      name: "新建视频2026-04-20-16-36",
      type: ProjectType.SMART_MIX,
      status: ProjectStatus.READY,
      comboCount: 10,
      at: "2026-04-22T15:02:24",
    },
    {
      id: "proj_0420_1151",
      name: "新建视频2026-04-20-11-51",
      type: ProjectType.SMART_MIX,
      status: ProjectStatus.DRAFT,
      comboCount: 0,
      at: "2026-04-22T15:02:19",
    },
  ];

  for (const p of projects) {
    const data = {
      ...base,
      name: p.name,
      type: p.type,
      status: p.status,
      comboCount: p.comboCount,
      width: 1080,
      height: 1920,
      createdAt: d(p.at),
      updatedAt: d(p.at),
    };
    await prisma.project.upsert({
      where: { id: p.id },
      update: data,
      create: { id: p.id, ...data },
    });
  }

  // ---- 投放分发 ----
  const distributions = [
    { id: "dist_1", title: "ID123962-04混剪", accountCount: 3, videoCount: 29, publishDone: 29, publishTotal: 29, views: 8252, likes: 47, at: "2026-05-06T11:23:38" },
    { id: "dist_2", title: "ID123949-04官号", accountCount: 1, videoCount: 2, publishDone: 2, publishTotal: 2, views: 1195, likes: 11, at: "2026-05-06T10:56:53" },
    { id: "dist_3", title: "ID123948-官号", accountCount: 2, videoCount: 4, publishDone: 4, publishTotal: 4, views: 2442, likes: 31, at: "2026-05-06T10:56:03" },
    { id: "dist_4", title: "ID123936-04混剪", accountCount: 3, videoCount: 20, publishDone: 0, publishTotal: 20, views: 0, likes: 0, at: "2026-05-06T10:17:23" },
    { id: "dist_5", title: "ID123934-0305混剪", accountCount: 6, videoCount: 80, publishDone: 80, publishTotal: 80, views: 29484, likes: 243, at: "2026-05-06T10:11:10" },
    { id: "dist_6", title: "ID123789-05人设", accountCount: 1, videoCount: 2, publishDone: 2, publishTotal: 2, views: 551, likes: 4, at: "2026-05-05T11:47:55" },
  ];
  for (const x of distributions) {
    const data = {
      ...base,
      title: x.title,
      platform: Platform.TIKTOK,
      accountCount: x.accountCount,
      videoCount: x.videoCount,
      publishDone: x.publishDone,
      publishTotal: x.publishTotal,
      views: x.views,
      likes: x.likes,
      createdAt: d(x.at),
    };
    await prisma.distribution.upsert({
      where: { id: x.id },
      update: data,
      create: { id: x.id, ...data },
    });
  }

  console.log(
    `Seeded: org=${org.name}, user=${user.nickname}, ` +
      `${projects.length} projects, ${distributions.length} distributions; ` +
      `cloud drive reset to empty (real OSS uploads only)`,
  );
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
