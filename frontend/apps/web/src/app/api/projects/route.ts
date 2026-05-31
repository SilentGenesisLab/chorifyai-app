import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma, Prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

const TYPE_MAP = {
  smart_mix: "SMART_MIX",
  super_mix: "SUPER_MIX",
  one_click: "ONE_CLICK",
} as const;

export async function GET(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });

  const url = new URL(req.url);
  const type = url.searchParams.get("type") ?? "all";
  const q = url.searchParams.get("q")?.trim();

  const where: Prisma.ProjectWhereInput = { orgId: ctx.orgId };
  if (type !== "all" && type in TYPE_MAP) {
    where.type = TYPE_MAP[type as keyof typeof TYPE_MAP];
  }
  if (q) where.name = { contains: q, mode: "insensitive" };

  const projects = await prisma.project.findMany({
    where,
    orderBy: { updatedAt: "desc" },
    take: 100,
    include: { createdBy: { select: { nickname: true } } },
  });

  return NextResponse.json({
    ok: true,
    projects: projects.map((p) => ({
      id: p.id,
      name: p.name,
      type: p.type,
      status: p.status,
      width: p.width,
      height: p.height,
      comboCount: p.comboCount,
      coverUrl: p.coverUrl,
      creator: p.createdBy?.nickname ?? "",
      updatedAt: p.updatedAt.toISOString(),
    })),
  });
}

const createSchema = z.object({
  name: z.string().min(1, "请输入工程名称").max(100),
  type: z.enum(["smart_mix", "super_mix", "one_click"]).default("smart_mix"),
  width: z.number().int().positive().max(8192).default(1080),
  height: z.number().int().positive().max(8192).default(1920),
});

export async function POST(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "请求体无效" }, { status: 400 });
  }
  const parsed = createSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: parsed.error.issues[0]?.message ?? "参数错误" },
      { status: 400 },
    );
  }
  const d = parsed.data;
  const project = await prisma.project.create({
    data: {
      name: d.name,
      type: TYPE_MAP[d.type],
      width: d.width,
      height: d.height,
      orgId: ctx.orgId,
      createdById: ctx.userId,
    },
  });
  return NextResponse.json({
    ok: true,
    project: { id: project.id, name: project.name, type: project.type },
  });
}
