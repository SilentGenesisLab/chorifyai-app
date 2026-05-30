import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/current-user";

export const runtime = "nodejs";

export async function GET() {
  const ctx = await getCurrentUser();
  if (!ctx) return NextResponse.json({ ok: false }, { status: 401 });
  return NextResponse.json({
    ok: true,
    user: {
      id: ctx.user.id,
      phone: ctx.user.phone,
      nickname: ctx.user.nickname,
      avatarUrl: ctx.user.avatarUrl,
    },
    org: ctx.currentOrg
      ? { id: ctx.currentOrg.id, name: ctx.currentOrg.name }
      : null,
  });
}
