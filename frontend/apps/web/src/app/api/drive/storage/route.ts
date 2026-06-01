import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { requireOrg } from "@/lib/api-auth";

export const runtime = "nodejs";

// Per-org storage quota. Flat constant for now (becomes plan-derived later).
const QUOTA_BYTES = 512 * 1024 ** 3; // 512 GB

export async function GET() {
  const ctx = await requireOrg();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });

  const [active, trashCount] = await Promise.all([
    prisma.asset.aggregate({
      where: { orgId: ctx.orgId, status: "ACTIVE" },
      _sum: { sizeBytes: true },
      _count: true,
    }),
    prisma.asset.count({ where: { orgId: ctx.orgId, status: "DELETED" } }),
  ]);

  return NextResponse.json({
    ok: true,
    usedBytes: active._sum.sizeBytes ?? 0,
    quotaBytes: QUOTA_BYTES,
    fileCount: active._count,
    trashCount,
  });
}
