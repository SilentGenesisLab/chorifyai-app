"use client";

import { useEffect, useRef, useState } from "react";
import { X, Upload, FolderPlus, Loader2, Cloud, Film, Check, Folder as FolderIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadFile } from "@/lib/upload";

export type ImportClip = { url: string; name: string; thumbnailUrl?: string | null; localPath?: string | null };
export type ImportGroup = { id: string; name: string; clips: ImportClip[] };

type DriveFolder = { id: string; name: string; count: number };

const rid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);
const VIDEO_RE = /\.(mp4|mov|webm|mkv|avi|m4v)$/i;
const HJSON = { "content-type": "application/json" };

/**
 * 添加镜头分组 —— 两种来源：
 *  · 上传：本地「文件夹 / 文件」上传到 OSS，并登记到云盘（之后可在云盘/导入里复用）
 *  · 导入云盘：勾选已有云盘文件夹，整夹作为一个镜头分组
 */
export function GroupImporter({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (groups: ImportGroup[]) => void;
}) {
  const [tab, setTab] = useState<"upload" | "drive">("upload");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  useEffect(() => {
    const el = folderRef.current;
    if (el) {
      el.setAttribute("webkitdirectory", "");
      el.setAttribute("directory", "");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setPicked(new Set());
    fetch("/api/drive/folders")
      .then((r) => r.json())
      .then((d) => {
        if (d?.ok) setFolders(d.folders);
      })
      .catch(() => {});
  }, [open]);

  if (!open) return null;

  // 上传本地文件 / 文件夹 → 传 OSS + 登记云盘 → 返回一个镜头分组
  async function uploadLocal(fileList: FileList | null, asFolder: boolean) {
    const all = Array.from(fileList ?? []);
    const files = all.filter((f) => f.type.startsWith("video/") || VIDEO_RE.test(f.name));
    if (!files.length) return;
    const first = files[0] as File & { webkitRelativePath?: string };
    const name = asFolder
      ? first.webkitRelativePath?.split("/")[0] || "上传分组"
      : `上传素材${new Date().toLocaleTimeString().slice(0, 5)}`;

    setBusy(true);
    setProgress({ done: 0, total: files.length });

    // 在云盘建一个同名文件夹，素材登记进去
    let folderId: string | undefined;
    try {
      const fr = await fetch("/api/drive/folders", {
        method: "POST",
        headers: HJSON,
        body: JSON.stringify({ name }),
      }).then((r) => r.json());
      folderId = fr?.folder?.id ?? fr?.id;
    } catch {
      /* 云盘登记失败不阻塞，仍可用 OSS url 合成 */
    }

    const clips: ImportClip[] = [];
    for (const f of files) {
      try {
        const up = await uploadFile(f, "video");
        clips.push({ url: up.url, name: f.name, thumbnailUrl: up.thumbnailUrl, localPath: up.localPath });
        fetch("/api/drive/assets", {
          method: "POST",
          headers: HJSON,
          body: JSON.stringify({
            name: f.name,
            type: "video",
            url: up.url,
            thumbnailUrl: up.thumbnailUrl ?? undefined,
            folderId,
          }),
        }).catch(() => {});
      } catch {
        /* 跳过失败的单条 */
      }
      setProgress((p) => (p ? { ...p, done: p.done + 1 } : p));
    }

    setBusy(false);
    setProgress(null);
    if (clips.length) onConfirm([{ id: rid(), name, clips }]);
    onClose();
  }

  // 导入云盘：勾选的文件夹 → 各取其视频作为一个镜头分组
  async function importDrive() {
    const ids = [...picked];
    if (!ids.length) return;
    setBusy(true);
    const groups: ImportGroup[] = [];
    for (const fid of ids) {
      const folder = folders.find((f) => f.id === fid);
      try {
        const d = await fetch(`/api/drive/assets?type=video&folderId=${fid}`).then((r) => r.json());
        const clips: ImportClip[] = (d.assets ?? [])
          .filter((a: { url?: string }) => a.url)
          .map((a: { url: string; name: string; thumbnailUrl?: string | null }) => ({
            url: a.url,
            name: a.name,
            thumbnailUrl: a.thumbnailUrl,
          }));
        if (clips.length) groups.push({ id: rid(), name: folder?.name ?? "分组", clips });
      } catch {
        /* skip */
      }
    }
    setBusy(false);
    if (groups.length) onConfirm(groups);
    onClose();
  }

  const togglePick = (id: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button type="button" aria-label="关闭" onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div className="relative z-10 flex h-[560px] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-surface text-foreground shadow-2xl">
        {/* tabs */}
        <div className="flex items-center gap-1 border-b border-border px-4">
          {([
            { k: "upload", l: "上传", I: Upload },
            { k: "drive", l: "导入云盘", I: Cloud },
          ] as const).map((t) => {
            const Icon = t.I;
            return (
              <button
                key={t.k}
                type="button"
                onClick={() => setTab(t.k)}
                className={cn(
                  "flex items-center gap-1.5 border-b-2 px-3 py-3 text-sm font-medium transition",
                  tab === t.k
                    ? "border-brand text-brand"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {t.l}
              </button>
            );
          })}
          <button type="button" onClick={onClose} className="ml-auto text-muted transition hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <input ref={folderRef} type="file" multiple hidden onChange={(e) => uploadLocal(e.target.files, true)} />
        <input ref={fileRef} type="file" accept="video/*" multiple hidden onChange={(e) => uploadLocal(e.target.files, false)} />

        {/* body */}
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {busy ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
              <Loader2 className="h-8 w-8 animate-spin text-brand" />
              <span className="text-sm">
                {progress ? `上传中 ${progress.done}/${progress.total}…` : "处理中…"}
              </span>
            </div>
          ) : tab === "upload" ? (
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => folderRef.current?.click()}
                className="flex aspect-[4/3] flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-strong transition hover:border-brand/60 hover:bg-brand-soft/40"
              >
                <FolderPlus className="h-9 w-9 text-brand" />
                <span className="text-sm font-medium">上传文件夹</span>
                <span className="text-xs text-muted">整个文件夹 = 一个镜头分组</span>
              </button>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex aspect-[4/3] flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-strong transition hover:border-brand/60 hover:bg-brand-soft/40"
              >
                <Upload className="h-9 w-9 text-brand" />
                <span className="text-sm font-medium">上传文件</span>
                <span className="text-xs text-muted">多个视频 = 一个镜头分组</span>
              </button>
              <p className="col-span-2 text-center text-xs text-muted">
                支持 mp4 / mov / webm…；上传后自动存入云盘（OSS），可在「云盘」查看和复用。
              </p>
            </div>
          ) : (
            <>
              {folders.length === 0 ? (
                <p className="py-20 text-center text-sm text-muted">
                  云盘里还没有文件夹。先到「上传」标签上传，或在云盘里新建。
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-3">
                  {folders.map((f) => {
                    const on = picked.has(f.id);
                    return (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => togglePick(f.id)}
                        className={cn(
                          "relative flex flex-col gap-2 rounded-xl border p-3 text-left transition",
                          on ? "border-brand bg-brand-soft" : "border-border bg-surface-muted/40 hover:bg-surface-muted",
                        )}
                      >
                        {on && (
                          <span className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-brand text-white">
                            <Check className="h-3 w-3" />
                          </span>
                        )}
                        <FolderIcon className="h-7 w-7 text-amber-500" />
                        <span className="truncate text-sm font-medium text-foreground">{f.name}</span>
                        <span className="flex items-center gap-1 text-xs text-muted">
                          <Film className="h-3 w-3" />
                          {f.count} 个文件
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        {/* footer (only on drive tab) */}
        {tab === "drive" && !busy && (
          <div className="flex items-center justify-between border-t border-border px-5 py-3">
            <span className="text-sm text-muted">已选 {picked.size} 个文件夹</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-border px-4 py-2 text-sm transition hover:bg-surface-muted"
              >
                取消
              </button>
              <button
                type="button"
                onClick={importDrive}
                disabled={!picked.size}
                className="brand-gradient rounded-lg px-5 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
              >
                导入为镜头分组
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
