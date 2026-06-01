export type UploadKind = "image" | "audio" | "video" | "file";

export interface UploadResult {
  ok: boolean;
  url: string;
  key: string;
  kind: string;
  name: string;
  size: number;
  contentType?: string | null;
  thumbnailUrl?: string | null;
}

/** Upload a file to the FastAPI backend (→ Aliyun OSS). Same-origin via Next rewrite. */
export async function uploadFile(
  file: File,
  kind: UploadKind,
): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("kind", kind);

  const res = await fetch("/api/upload", { method: "POST", body: fd });
  if (!res.ok) {
    let msg = "上传失败";
    try {
      const e = await res.json();
      msg = e.detail || e.error || msg;
    } catch {
      /* ignore */
    }
    throw new Error(typeof msg === "string" ? msg : "上传失败");
  }
  return res.json();
}
