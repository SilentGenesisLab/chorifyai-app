import { sendViaMock } from "./mock";
import { sendViaAliyun } from "./aliyun";

/** Send a login verification code via the configured provider. */
export async function sendLoginCode(phone: string, code: string): Promise<void> {
  const provider = process.env.SMS_PROVIDER ?? "mock";
  if (provider === "aliyun") return sendViaAliyun(phone, code);
  return sendViaMock(phone, code);
}

/** 6-digit numeric code. */
export function generateCode(): string {
  return String(Math.floor(100000 + Math.random() * 900000));
}
