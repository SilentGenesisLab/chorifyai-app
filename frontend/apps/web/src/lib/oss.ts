/**
 * Object storage (Aliyun OSS).
 *   OSS_PROVIDER=mock   -> deterministic fake URLs, no network (local dev)
 *   OSS_PROVIDER=aliyun -> real uploads to bucket `chorify-nova`
 *
 * The SDK is loaded lazily so the mock path stays dependency-free.
 */
export interface PutResult {
  key: string;
  url: string;
}

function req(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env ${name}`);
  return v;
}

function publicBase(): string {
  const base =
    process.env.ALIYUN_OSS_PUBLIC_BASE_URL ||
    `https://${process.env.ALIYUN_OSS_BUCKET || "chorify-nova"}.${
      process.env.ALIYUN_OSS_REGION || "oss-cn-shenzhen"
    }.aliyuncs.com`;
  return base.replace(/\/$/, "");
}

async function getClient() {
  const mod = await import("ali-oss");
  const OSS = (mod as { default: typeof import("ali-oss") }).default ?? mod;
  return new OSS({
    region: process.env.ALIYUN_OSS_REGION || "oss-cn-shenzhen",
    accessKeyId: req("ALIYUN_OSS_ACCESS_KEY_ID"),
    accessKeySecret: req("ALIYUN_OSS_ACCESS_KEY_SECRET"),
    bucket: process.env.ALIYUN_OSS_BUCKET || "chorify-nova",
    secure: true,
  });
}

/** Upload an object and return its public URL. */
export async function putObject(
  key: string,
  body: Buffer | Uint8Array | string,
  contentType?: string,
): Promise<PutResult> {
  const provider = process.env.OSS_PROVIDER ?? "mock";

  if (provider !== "aliyun") {
    const base = process.env.ALIYUN_OSS_PUBLIC_BASE_URL || "https://mock-oss.local";
    return { key, url: `${base.replace(/\/$/, "")}/${key}` };
  }

  const client = await getClient();
  const buf =
    typeof body === "string"
      ? Buffer.from(body)
      : Buffer.isBuffer(body)
        ? body
        : Buffer.from(body);
  await client.put(
    key,
    buf,
    contentType ? { headers: { "Content-Type": contentType } } : undefined,
  );
  return { key, url: `${publicBase()}/${key}` };
}

/** Generate a temporary signed URL for a private object. */
export async function getSignedUrl(
  key: string,
  expiresSec = 3600,
): Promise<string> {
  const provider = process.env.OSS_PROVIDER ?? "mock";
  if (provider !== "aliyun") {
    const base = process.env.ALIYUN_OSS_PUBLIC_BASE_URL || "https://mock-oss.local";
    return `${base.replace(/\/$/, "")}/${key}`;
  }
  const client = await getClient();
  return client.signatureUrl(key, { expires: expiresSec });
}
