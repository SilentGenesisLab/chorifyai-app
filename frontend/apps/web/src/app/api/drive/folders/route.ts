import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

// ---------------------------------------------------------------- list
export async function GET() {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const folders = await prisma.folder.findMany({
    where: { orgId: ctx.orgId },
    orderBy: { createdAt: "asc" },
    include: { _count: { select: { assets: { where: { status: "ACTIVE" } } } } },
  });
  return NextResponse.json({
    ok: true,
    folders: folders.map((f) => ({
      id: f.id,
      name: f.name,
      parentId: f.parentId,
      count: f._count.assets,
    })),
  });
}

// ---------------------------------------------------------------- create
const createSchema = z.object({
  name: z.string().min(1, "请输入文件夹名称").max(60),
  parentId: z.string().nullish(),
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

  // A provided parent must belong to the same org.
  if (parsed.data.parentId) {
    const parent = await prisma.folder.findFirst({
      where: { id: parsed.data.parentId, orgId: ctx.orgId },
      select: { id: true },
    });
    if (!parent) {
      return NextResponse.json({ ok: false, error: "父文件夹不存在" }, { status: 400 });
    }
  }

  const folder = await prisma.folder.create({
    data: {
      name: parsed.data.name,
      parentId: parsed.data.parentId ?? null,
      orgId: ctx.orgId,
      createdById: ctx.userId,
    },
  });
  return NextResponse.json({
    ok: true,
    folder: { id: folder.id, name: folder.name, parentId: folder.parentId },
  });
}

// ---------------------------------------------------------------- rename
const renameSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1, "请输入文件夹名称").max(60),
});

export async function PATCH(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const parsed = renameSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: parsed.error.issues[0]?.message ?? "参数错误" },
      { status: 400 },
    );
  }
  const folder = await prisma.folder.findFirst({
    where: { id: parsed.data.id, orgId: ctx.orgId },
    select: { id: true },
  });
  if (!folder) return NextResponse.json({ ok: false, error: "文件夹不存在" }, { status: 404 });

  await prisma.folder.update({
    where: { id: parsed.data.id },
    data: { name: parsed.data.name },
  });
  return NextResponse.json({ ok: true });
}

// ---------------------------------------------------------------- delete (folder + subfolders;
// contained files are moved to 回收站, i.e. soft-deleted and recoverable)
const deleteSchema = z.object({ id: z.string().min(1) });

export async function DELETE(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const parsed = deleteSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "参数错误" }, { status: 400 });
  }

  const root = await prisma.folder.findFirst({
    where: { id: parsed.data.id, orgId: ctx.orgId },
    select: { id: true },
  });
  if (!root) return NextResponse.json({ ok: false, error: "文件夹不存在" }, { status: 404 });

  // Collect this folder + all descendants (BFS over the org's folder tree).
  const all = await prisma.folder.findMany({
    where: { orgId: ctx.orgId },
    select: { id: true, parentId: true },
  });
  const childrenOf = new Map<string, string[]>();
  for (const f of all) {
    if (!f.parentId) continue;
    (childrenOf.get(f.parentId) ?? childrenOf.set(f.parentId, []).get(f.parentId)!).push(f.id);
  }
  const toDelete: string[] = [];
  const stack = [root.id];
  while (stack.length) {
    const cur = stack.pop()!;
    toDelete.push(cur);
    for (const c of childrenOf.get(cur) ?? []) stack.push(c);
  }

  // Soft-delete contained files first (so they survive in 回收站), then drop folders.
  await prisma.$transaction([
    prisma.asset.updateMany({
      where: { orgId: ctx.orgId, folderId: { in: toDelete }, status: "ACTIVE" },
      data: { status: "DELETED" },
    }),
    prisma.folder.deleteMany({ where: { orgId: ctx.orgId, id: { in: toDelete } } }),
  ]);

  return NextResponse.json({ ok: true, deletedFolders: toDelete.length });
}
