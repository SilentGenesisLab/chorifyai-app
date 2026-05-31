import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma, Prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

// 素材生产产物列表（按组织查询，进入页面时回显真实数据）
export async function GET(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });

  const url = new URL(req.url);
  const moduleq = url.searchParams.get("module");
  const kind = url.searchParams.get("kind");

  const where: Prisma.GenerationWhereInput = { orgId: ctx.orgId };
  if (moduleq) where.module = moduleq;
  if (kind) where.kind = kind;

  const rows = await prisma.generation.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 200,
  });

  return NextResponse.json({
    ok: true,
    generations: rows.map((g) => ({
      id: g.id,
      type: g.module,
      kind: g.kind,
      status: "succeeded",
      text: g.text,
      voiceName: g.voiceName,
      resultUrl: g.resultUrl,
      thumbnailUrl: g.thumbnailUrl,
      durationSec: g.durationSec,
      createdAt: g.createdAt.toISOString(),
    })),
  });
}

const createSchema = z.object({
  module: z.string().min(1).max(40),
  kind: z.enum(["audio", "video", "image"]),
  text: z.string().max(2000).nullish(),
  voiceName: z.string().max(200).nullish(),
  resultUrl: z.string().url().nullish(),
  thumbnailUrl: z.string().url().nullish(),
  durationSec: z.number().int().nonnegative().nullish(),
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
  const g = await prisma.generation.create({
    data: {
      module: d.module,
      kind: d.kind,
      text: d.text ?? null,
      voiceName: d.voiceName ?? null,
      resultUrl: d.resultUrl ?? null,
      thumbnailUrl: d.thumbnailUrl ?? null,
      durationSec: d.durationSec ?? null,
      orgId: ctx.orgId,
      createdById: ctx.userId,
    },
  });
  return NextResponse.json({ ok: true, id: g.id, createdAt: g.createdAt.toISOString() });
}
