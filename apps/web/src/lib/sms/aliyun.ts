/**
 * Aliyun SMS (Dysmsapi 2017-05-25). Loaded lazily so the mock path stays
 * dependency-free. Enable with SMS_PROVIDER=aliyun + ALIYUN_SMS_* env vars.
 *
 * The SMS template (SMS_296885677) expects a `${code}` variable, so the
 * templateParam is { code }.
 */
function req(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env ${name}`);
  return v;
}

export async function sendViaAliyun(phone: string, code: string): Promise<void> {
  const accessKeyId = req("ALIYUN_SMS_ACCESS_KEY_ID");
  const accessKeySecret = req("ALIYUN_SMS_ACCESS_KEY_SECRET");
  const signName = req("ALIYUN_SMS_SIGN_NAME");
  const templateCode = req("ALIYUN_SMS_TEMPLATE_CODE");

  const Dysmsapi = await import("@alicloud/dysmsapi20170525");
  const OpenApi = await import("@alicloud/openapi-client");

  const Client = Dysmsapi.default;
  const config = new OpenApi.Config({ accessKeyId, accessKeySecret });
  config.endpoint = process.env.ALIYUN_SMS_ENDPOINT || "dysmsapi.aliyuncs.com";

  const client = new Client(config);
  const request = new Dysmsapi.SendSmsRequest({
    phoneNumbers: phone,
    signName,
    templateCode,
    templateParam: JSON.stringify({ code }),
  });

  const res = await client.sendSms(request);
  const body = res.body;
  if (!body || body.code !== "OK") {
    throw new Error(
      `Aliyun SMS failed: ${body?.code ?? "unknown"} ${body?.message ?? ""}`.trim(),
    );
  }
}
