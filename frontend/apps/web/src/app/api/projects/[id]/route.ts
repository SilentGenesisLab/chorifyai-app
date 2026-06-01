import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma, Prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const { id } = await params;
  const p = await prisma.project.findFirst({ where: { id, orgId: ctx.orgId } });
  if (!p) return NextResponse.json({ ok: false }, { status: 404 });
  return NextResponse.json({
    ok: true,
    project: {
      id: p.id,
      name: p.name,
      type: p.type,
      status: p.status,
      width: p.width,
      height: p.height,
      comboCount: p.comboCount,
      config: p.config,
      updatedAt: p.updatedAt.toISOString(),
    },
  });
}

const patchSchema = z.object({
  name: z.string().min(1).max(100).optional(),
  comboCount: z.number().int().nonnegative().optional(),
  config: z.unknown().optional(), // 编辑器配置（镜头分组 + 片段）
});

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const { id } = await params;
  const parsed = patchSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "参数错误" }, { status: 400 });
  }
  const data: Prisma.ProjectUpdateManyMutationInput = {};
  if (parsed.data.name !== undefined) data.name = parsed.data.name;
  if (parsed.data.comboCount !== undefined) data.comboCount = parsed.data.comboCount;
  if (parsed.data.config !== undefined) {
    data.config = parsed.data.config as Prisma.InputJsonValue;
  }
  const r = await prisma.project.updateMany({
    where: { id, orgId: ctx.orgId },
    data,
  });
  if (r.count === 0) return NextResponse.json({ ok: false }, { status: 404 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  const { id } = await params;
  await prisma.project.deleteMany({ where: { id, orgId: ctx.orgId } });
  return NextResponse.json({ ok: true });
}
