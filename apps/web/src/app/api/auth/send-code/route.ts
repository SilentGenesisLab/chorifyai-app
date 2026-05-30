import { NextResponse } from "next/server";
import { z } from "zod";
import { redis } from "@/lib/redis";
import { sendLoginCode, generateCode } from "@/lib/sms";

export const runtime = "nodejs";

const schema = z.object({
  phone: z.string().regex(/^1[3-9]\d{9}$/, "手机号格式不正确"),
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
    return NextResponse.json(
      { ok: false, error: parsed.error.issues[0]?.message ?? "参数错误" },
      { status: 400 },
    );
  }
  const { phone } = parsed.data;

  // 60s resend cooldown
  const rateKey = `sms:rate:${phone}`;
  if (await redis.get(rateKey)) {
    return NextResponse.json(
      { ok: false, error: "请求过于频繁，请稍后再试" },
      { status: 429 },
    );
  }

  const code = generateCode();

  // Send first; only persist the code + cooldown if delivery succeeded, so a
  // provider failure (rate limit, transient error) lets the user retry cleanly
  // instead of surfacing a 500.
  try {
    await sendLoginCode(phone, code);
  } catch (err) {
    console.error("[send-code] SMS delivery failed:", err);
    return NextResponse.json(
      { ok: false, error: "短信发送失败，请稍后重试" },
      { status: 502 },
    );
  }

  await redis.set(`sms:code:${phone}`, code, "EX", 300);
  await redis.set(rateKey, "1", "EX", 60);

  // In dev with the mock provider, surface the code so you can log in fast.
  const devCode =
    (process.env.SMS_PROVIDER ?? "mock") === "mock" &&
    process.env.NODE_ENV !== "production"
      ? code
      : undefined;

  return NextResponse.json({ ok: true, devCode });
}
