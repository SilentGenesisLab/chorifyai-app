import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma, Prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

const TYPE_MAP = {
  material: "MATERIAL",
  project: "PROJECT",
  finished: "FINISHED",
  video: "VIDEO",
  image: "IMAGE",
  audio: "AUDIO",
} as const;

export async function GET(req: Request) {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });

  const url = new URL(req.url);
  const type = url.searchParams.get("type") ?? "all";
  const folderId = url.searchParams.get("folderId");
  const q = url.searchParams.get("q")?.trim();

  const where: Prisma.AssetWhereInput = { orgId: ctx.orgId, status: "ACTIVE" };
  if (type !== "all" && type in TYPE_MAP) {
    where.type = TYPE_MAP[type as keyof typeof TYPE_MAP];
  }
  if (folderId) where.folderId = folderId;
  if (q) where.name = { contains: q, mode: "insensitive" };

  const assets = await prisma.asset.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 300,
  });

  return NextResponse.json({
    ok: true,
    assets: assets.map((a) => ({
      id: a.id,
      name: a.name,
      type: a.type,
      url: a.url,
      thumbnailUrl: a.thumbnailUrl,
      durationSec: a.durationSec,
      folderId: a.folderId,
      createdAt: a.createdAt.toISOString(),
    })),
  });
}

const createSchema = z.object({
  name: z.string().min(1).max(200),
  type: z.enum(["material", "project", "finished", "video", "image", "audio"]),
  url: z.string().url().optional(),
  thumbnailUrl: z.string().url().nullish(),
  durationSec: z.number().int().nonnegative().nullish(),
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
  const asset = await prisma.asset.create({
    data: {
      name: d.name,
      type: TYPE_MAP[d.type],
      url: d.url,
      thumbnailUrl: d.thumbnailUrl ?? null,
      durationSec: d.durationSec ?? null,
      folderId: d.folderId ?? null,
      orgId: ctx.orgId,
      createdById: ctx.userId,
    },
  });
  return NextResponse.json({ ok: true, asset: { id: asset.id, name: asset.name } });
}
