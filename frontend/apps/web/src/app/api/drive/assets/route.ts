import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma, Prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";
import { deleteOssObjects } from "@/lib/oss-delete";

export const runtime = "nodejs";

const TYPE_MAP = {
  material: "MATERIAL",
  project: "PROJECT",
  finished: "FINISHED",
  video: "VIDEO",
  image: "IMAGE",
  audio: "AUDIO",
} as const;

// ---------------------------------------------------------------- list
export async function GET(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });

  const url = new URL(req.url);
  const type = url.searchParams.get("type") ?? "all";
  const folderId = url.searchParams.get("folderId");
  const q = url.searchParams.get("q")?.trim();
  const scope = url.searchParams.get("scope") ?? "all"; // all | mine | trash

  const where: Prisma.AssetWhereInput = {
    orgId: ctx.orgId,
    status: scope === "trash" ? "DELETED" : "ACTIVE",
  };
  if (scope === "mine") where.createdById = ctx.userId;
  if (type === "video") {
    // 成片(FINISHED)本质也是视频 —— 类型只是标签，视频标签页里都能看到
    where.type = { in: ["VIDEO", "FINISHED"] as ("VIDEO" | "FINISHED")[] };
  } else if (type !== "all" && type in TYPE_MAP) {
    where.type = TYPE_MAP[type as keyof typeof TYPE_MAP];
  }
  if (folderId && scope !== "trash") where.folderId = folderId;
  if (q) where.name = { contains: q, mode: "insensitive" };

  const assets = await prisma.asset.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 500,
  });

  const items: Record<string, unknown>[] = assets.map((a) => ({
    id: a.id,
    name: a.name,
    type: a.type,
    url: a.url,
    thumbnailUrl: a.thumbnailUrl,
    durationSec: a.durationSec,
    sizeBytes: a.sizeBytes,
    folderId: a.folderId,
    createdAt: a.createdAt.toISOString(),
  }));

  // 合成量产「工程」作为云盘条目展示在「工程」标签（点开进编辑器）。
  // 只在工程标签出现，不进文件夹/回收站；以 Project 表为准，不占存储计数。
  if (scope !== "trash" && !folderId && type === "project") {
    const projWhere: Prisma.ProjectWhereInput = { orgId: ctx.orgId };
    if (scope === "mine") projWhere.createdById = ctx.userId;
    if (q) projWhere.name = { contains: q, mode: "insensitive" };
    const projects = await prisma.project.findMany({
      where: projWhere,
      orderBy: { updatedAt: "desc" },
      take: 200,
    });
    const projItems = projects.map((p) => ({
      id: p.id,
      name: p.name,
      type: "PROJECT",
      url: null,
      thumbnailUrl: p.coverUrl,
      durationSec: null,
      sizeBytes: null,
      folderId: null,
      isProject: true,
      createdAt: p.createdAt.toISOString(),
    }));
    items.unshift(...projItems);
  }

  return NextResponse.json({ ok: true, assets: items });
}

// ---------------------------------------------------------------- create
const createSchema = z.object({
  name: z.string().min(1).max(200),
  type: z.enum(["material", "project", "finished", "video", "image", "audio"]),
  url: z.string().url().optional(),
  ossKey: z.string().nullish(),
  thumbnailUrl: z.string().url().nullish(),
  durationSec: z.number().int().nonnegative().nullish(),
  sizeBytes: z.number().int().nonnegative().nullish(),
  mimeType: z.string().max(200).nullish(),
  folderId: z.string().nullish(),
});

export async function POST(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const parsed = createSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: parsed.error.issues[0]?.message ?? "参数错误" },
      { status: 400 },
    );
  }
  const d = parsed.data;

  // Guard against cross-org folder assignment.
  if (d.folderId) {
    const folder = await prisma.folder.findFirst({
      where: { id: d.folderId, orgId: ctx.orgId },
      select: { id: true },
    });
    if (!folder) {
      return NextResponse.json({ ok: false, error: "目标文件夹不存在" }, { status: 400 });
    }
  }

  const asset = await prisma.asset.create({
    data: {
      name: d.name,
      type: TYPE_MAP[d.type],
      url: d.url,
      ossKey: d.ossKey ?? null,
      thumbnailUrl: d.thumbnailUrl ?? null,
      durationSec: d.durationSec ?? null,
      sizeBytes: d.sizeBytes ?? null,
      mimeType: d.mimeType ?? null,
      folderId: d.folderId ?? null,
      orgId: ctx.orgId,
      createdById: ctx.userId,
    },
  });
  return NextResponse.json({ ok: true, asset: { id: asset.id, name: asset.name } });
}

// ---------------------------------------------------------------- rename / move / restore
const patchSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1).max(200).optional(),
  folderId: z.string().nullable().optional(), // null = move to root
  restore: z.boolean().optional(), // trash -> active
});

export async function PATCH(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const parsed = patchSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: parsed.error.issues[0]?.message ?? "参数错误" },
      { status: 400 },
    );
  }
  const { id, name, folderId, restore } = parsed.data;

  const existing = await prisma.asset.findFirst({
    where: { id, orgId: ctx.orgId },
    select: { id: true },
  });
  if (!existing) return NextResponse.json({ ok: false, error: "文件不存在" }, { status: 404 });

  if (folderId) {
    const folder = await prisma.folder.findFirst({
      where: { id: folderId, orgId: ctx.orgId },
      select: { id: true },
    });
    if (!folder) {
      return NextResponse.json({ ok: false, error: "目标文件夹不存在" }, { status: 400 });
    }
  }

  const data: Prisma.AssetUpdateInput = {};
  if (name !== undefined) data.name = name;
  if (folderId !== undefined) {
    data.folder = folderId ? { connect: { id: folderId } } : { disconnect: true };
  }
  if (restore) data.status = "ACTIVE";

  await prisma.asset.update({ where: { id }, data });
  return NextResponse.json({ ok: true });
}

// ---------------------------------------------------------------- delete (trash or permanent)
const deleteSchema = z.object({
  id: z.string().min(1),
  permanent: z.boolean().optional(),
});

export async function DELETE(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const parsed = deleteSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: parsed.error.issues[0]?.message ?? "参数错误" },
      { status: 400 },
    );
  }
  const { id, permanent } = parsed.data;

  const existing = await prisma.asset.findFirst({
    where: { id, orgId: ctx.orgId },
    select: { id: true, ossKey: true },
  });
  if (!existing) return NextResponse.json({ ok: false, error: "文件不存在" }, { status: 404 });

  if (permanent) {
    await deleteOssObjects([existing.ossKey]);
    await prisma.asset.delete({ where: { id } });
  } else {
    await prisma.asset.update({ where: { id }, data: { status: "DELETED" } });
  }
  return NextResponse.json({ ok: true });
}
