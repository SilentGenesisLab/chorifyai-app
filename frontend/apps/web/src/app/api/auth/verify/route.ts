import { NextResponse } from "next/server";
import { z } from "zod";
import { redis } from "@/lib/redis";
import { prisma } from "@/lib/db";
import { setSessionCookie } from "@/lib/auth/session";
import { DEMO_ORG_ID, DEMO_ORG_NAME } from "@/lib/constants";

export const runtime = "nodejs";

const schema = z.object({
  phone: z.string().regex(/^1[3-9]\d{9}$/),
  code: z.string().regex(/^\d{6}$/),
});

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "请求体无效" }, { status: 400 });
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "参数错误" }, { status: 400 });
  }
  const { phone, code } = parsed.data;

  const stored = await redis.get(`sms:code:${phone}`);
  if (!stored || stored !== code) {
    return NextResponse.json(
      { ok: false, error: "验证码错误或已过期" },
      { status: 401 },
    );
  }
  await redis.del(`sms:code:${phone}`);

  // Ensure the demo org exists so login works even before `pnpm db:seed`.
  await prisma.organization.upsert({
    where: { id: DEMO_ORG_ID },
    update: {},
    create: { id: DEMO_ORG_ID, name: DEMO_ORG_NAME, plan: "ENTERPRISE" },
  });

  const user = await prisma.user.upsert({
    where: { phone },
    update: { lastLoginAt: new Date() },
    create: {
      phone,
      nickname: `用户${phone.slice(-4)}`,
      lastLoginAt: new Date(),
    },
  });

  await prisma.membership.upsert({
    where: { userId_orgId: { userId: user.id, orgId: DEMO_ORG_ID } },
    update: {},
    create: { userId: user.id, orgId: DEMO_ORG_ID, role: "MEMBER" },
  });

  await setSessionCookie({
    userId: user.id,
    phone: user.phone,
    orgId: DEMO_ORG_ID,
  });

  return NextResponse.json({
    ok: true,
    user: { id: user.id, phone: user.phone, nickname: user.nickname },
  });
}
