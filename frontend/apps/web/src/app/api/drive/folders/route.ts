import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

export async function GET() {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const folders = await prisma.folder.findMany({
    where: { orgId: ctx.orgId },
    orderBy: { createdAt: "asc" },
    include: { _count: { select: { assets: true } } },
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
  const folder = await prisma.folder.create({
    data: {
      name: parsed.data.name,
      parentId: parsed.data.parentId ?? null,
      orgId: ctx.orgId,
      createdById: ctx.userId,
    },
  });
  return NextResponse.json({ ok: true, folder: { id: folder.id, name: folder.name } });
}
