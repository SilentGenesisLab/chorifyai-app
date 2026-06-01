/**
 * Server-side helper to remove objects from Aliyun OSS.
 *
 * The web app's own `lib/oss.ts` runs with OSS_PROVIDER=mock in dev, so all
 * *real* OSS I/O is owned by the FastAPI backend (which holds the prod creds).
 * Uploads already go through `/api/upload`; permanent deletes call the matching
 * `/api/upload/delete` endpoint here. Best-effort — never throws, so a failed
 * OSS cleanup can't block the DB delete.
 */
const BASE = process.env.AI_SERVICE_URL ?? "http://127.0.0.1:8000";

export async function deleteOssObjects(keys: (string | null | undefined)[]): Promise<void> {
  const ks = keys.filter((k): k is string => Boolean(k));
  if (ks.length === 0) return;
  try {
    await fetch(`${BASE}/api/upload/delete`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ keys: ks }),
    });
  } catch (e) {
    console.error("[drive] OSS object delete failed (keys kept orphaned):", e);
  }
}
