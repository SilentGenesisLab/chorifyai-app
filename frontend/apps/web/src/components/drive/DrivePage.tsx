"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Files,
  User,
  Trash2,
  Folder as FolderIcon,
  FolderPlus,
  Search,
  Upload,
  Loader2,
  Play,
  MoreVertical,
  Pencil,
  Trash,
  RotateCcw,
  Check,
  X,
  ChevronDown,
  FileUp,
  FolderUp,
} from "lucide-react";
import { cn, formatDateTime, formatDuration, formatBytes } from "@/lib/utils";
import { tileGradient } from "@/components/material/types";
import { uploadFile, type UploadKind, type UploadResult } from "@/lib/upload";

type Folder = { id: string; name: string; parentId?: string | null; count: number };
type Asset = {
  id: string;
  name: string;
  type: string;
  url?: string | null;
  thumbnailUrl?: string | null;
  durationSec?: number | null;
  sizeBytes?: number | null;
  folderId?: string | null;
  isProject?: boolean; // 合成量产工程（云盘里点开进编辑器）
  createdAt: string;
};
type Scope = "all" | "mine" | "trash";
type Storage = { usedBytes: number; quotaBytes: number; fileCount: number; trashCount: number };

const TYPE_TABS = [
  { key: "all", label: "全部" },
  { key: "material", label: "素材" },
  { key: "project", label: "工程" },
  { key: "finished", label: "成片" },
  { key: "video", label: "视频" },
  { key: "image", label: "图片" },
  { key: "audio", label: "音频" },
];

const TAG: Record<string, string> = {
  PROJECT: "工程",
  FINISHED: "成片",
  VIDEO: "视频",
  IMAGE: "图片",
  AUDIO: "音频",
  MATERIAL: "素材",
};

function bucketOf(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sod = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const today = sod(now);
  const dDay = sod(d);
  const day = 86400000;
  if (dDay === today) return "今天";
  if (dDay === today - day) return "昨天";
  if (dDay > today - 7 * day) return "近7天";
  return "更早";
}
const ORDER = ["今天", "昨天", "近7天", "更早"];

function kindOf(f: File): UploadKind {
  const t = f.type || "";
  if (t.startsWith("video")) return "video";
  if (t.startsWith("audio")) return "audio";
  if (t.startsWith("image")) return "image";
  return "file";
}

/** Read media duration in the browser (no backend probe needed). */
function readDuration(f: File): Promise<number | undefined> {
  const isVideo = (f.type || "").startsWith("video");
  const isAudio = (f.type || "").startsWith("audio");
  if (!isVideo && !isAudio) return Promise.resolve(undefined);
  return new Promise((resolve) => {
    const el = document.createElement(isVideo ? "video" : "audio");
    const src = URL.createObjectURL(f);
    const done = (v?: number) => {
      URL.revokeObjectURL(src);
      resolve(v);
    };
    el.preload = "metadata";
    el.onloadedmetadata = () =>
      done(Number.isFinite(el.duration) ? Math.round(el.duration) : undefined);
    el.onerror = () => done(undefined);
    el.src = src;
  });
}

/** Upload by detected kind; fall back to generic "file" if the backend rejects the type. */
async function uploadSmart(f: File): Promise<{ up: UploadResult; kind: UploadKind }> {
  const k = kindOf(f);
  try {
    return { up: await uploadFile(f, k), kind: k };
  } catch (e) {
    if (k === "file") throw e;
    return { up: await uploadFile(f, "file"), kind: "file" };
  }
}

export function DrivePage() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("all");
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [storage, setStorage] = useState<Storage | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");

  const [uploadMenu, setUploadMenu] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  // The folder picker needs non-standard attributes set imperatively.
  useEffect(() => {
    const el = folderRef.current;
    if (el) {
      el.setAttribute("webkitdirectory", "");
      el.setAttribute("directory", "");
      el.setAttribute("mozdirectory", "");
    }
  }, []);

  const loadFolders = useCallback(async () => {
    const r = await fetch("/api/drive/folders");
    const d = await r.json();
    if (d.ok) setFolders(d.folders);
  }, []);

  const loadStorage = useCallback(async () => {
    const r = await fetch("/api/drive/storage");
    const d = await r.json();
    if (d.ok) setStorage(d);
  }, []);

  const loadAssets = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (scope === "mine" || scope === "trash") p.set("scope", scope);
      if (type !== "all") p.set("type", type);
      if (activeFolder && scope === "all") p.set("folderId", activeFolder);
      if (q.trim()) p.set("q", q.trim());
      const r = await fetch(`/api/drive/assets?${p.toString()}`);
      const d = await r.json();
      if (d.ok) setAssets(d.assets);
    } finally {
      setLoading(false);
    }
  }, [scope, activeFolder, type, q]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadAssets(), loadFolders(), loadStorage()]);
  }, [loadAssets, loadFolders, loadStorage]);

  useEffect(() => {
    loadFolders();
    loadStorage();
  }, [loadFolders, loadStorage]);

  // Reload the grid when the active view changes (search is triggered on Enter).
  useEffect(() => {
    loadAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, activeFolder, type]);

  const grouped = useMemo(() => {
    const g: Record<string, Asset[]> = {};
    for (const a of assets) {
      const b = bucketOf(a.createdAt);
      (g[b] ??= []).push(a);
    }
    return g;
  }, [assets]);

  // ----------------------------------------------------------------- upload
  async function createFolderApi(name: string, parentId: string | null): Promise<Folder | null> {
    const r = await fetch("/api/drive/folders", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, parentId }),
    });
    const d = await r.json();
    return d.ok ? d.folder : null;
  }

  async function handleUpload(list: FileList | null, asFolder: boolean) {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    setUploading(true);
    // Recreate the dragged folder tree once, mapping each relative dir → folder id.
    const pathToId = new Map<string, string | null>();
    pathToId.set("", activeFolder);
    try {
      let done = 0;
      for (const f of files) {
        let parentId = activeFolder ?? null;
        const rel = asFolder ? f.webkitRelativePath : "";
        if (rel) {
          const parts = rel.split("/");
          parts.pop(); // drop the file name
          let prefix = "";
          for (const part of parts) {
            prefix = prefix ? `${prefix}/${part}` : part;
            if (!pathToId.has(prefix)) {
              const created = await createFolderApi(part, parentId);
              pathToId.set(prefix, created?.id ?? parentId);
            }
            parentId = pathToId.get(prefix) ?? parentId;
          }
        }
        setUploadMsg(`上传中 ${done + 1}/${files.length}：${f.name}`);
        const duration = await readDuration(f);
        const { up, kind } = await uploadSmart(f);
        await fetch("/api/drive/assets", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            name: up.name || f.name,
            type: kind === "file" ? "material" : kind,
            url: up.url,
            ossKey: up.key,
            thumbnailUrl: up.thumbnailUrl ?? null,
            sizeBytes: up.size,
            mimeType: up.contentType ?? f.type ?? null,
            durationSec: duration ?? null,
            folderId: parentId,
          }),
        });
        done++;
      }
      await refreshAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
      setUploadMsg("");
    }
  }

  // ----------------------------------------------------------------- folder CRUD
  async function submitNewFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    await createFolderApi(name, null);
    setNewFolderName("");
    setNewFolderOpen(false);
    await loadFolders();
  }

  async function renameFolder(id: string) {
    const name = renameValue.trim();
    setRenamingId(null);
    if (!name) return;
    await fetch("/api/drive/folders", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id, name }),
    });
    await loadFolders();
  }

  async function deleteFolder(f: Folder) {
    const msg =
      f.count > 0
        ? `删除文件夹「${f.name}」？其中 ${f.count} 个文件将移入回收站。`
        : `删除文件夹「${f.name}」？`;
    if (!confirm(msg)) return;
    await fetch("/api/drive/folders", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: f.id }),
    });
    if (activeFolder === f.id) setActiveFolder(null);
    await refreshAll();
  }

  // ----------------------------------------------------------------- asset actions
  async function renameAsset(a: Asset) {
    const name = prompt("重命名文件", a.name)?.trim();
    if (!name || name === a.name) return;
    await fetch("/api/drive/assets", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: a.id, name }),
    });
    await loadAssets();
  }

  async function trashAsset(a: Asset) {
    await fetch("/api/drive/assets", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: a.id }),
    });
    await refreshAll();
  }

  async function restoreAsset(a: Asset) {
    await fetch("/api/drive/assets", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: a.id, restore: true }),
    });
    await refreshAll();
  }

  async function deleteAssetForever(a: Asset) {
    if (!confirm(`彻底删除「${a.name}」？此操作不可恢复，将从云端移除该文件。`)) return;
    await fetch("/api/drive/assets", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: a.id, permanent: true }),
    });
    await refreshAll();
  }

  function selectScope(s: Scope) {
    setScope(s);
    setActiveFolder(null);
  }

  const usedPct = storage ? Math.min(100, (storage.usedBytes / storage.quotaBytes) * 100) : 0;
  const isTrash = scope === "trash";

  return (
    <div className="flex h-full min-h-0">
      {/* left: scopes + folders + storage */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-border p-4">
        <div className="space-y-0.5">
          <Scope
            icon={Files}
            label="全部文件"
            count={storage?.fileCount ?? 0}
            active={scope === "all" && !activeFolder}
            onClick={() => selectScope("all")}
          />
          <Scope
            icon={User}
            label="我创建的"
            count={storage?.fileCount ?? 0}
            active={scope === "mine"}
            onClick={() => selectScope("mine")}
          />
          <Scope
            icon={Trash2}
            label="回收站"
            count={storage?.trashCount ?? 0}
            active={scope === "trash"}
            onClick={() => selectScope("trash")}
          />
        </div>

        <div className="ink-rule my-4" />

        <div className="mb-2 flex items-center justify-between px-1">
          <p className="text-sm text-muted">全部文件夹</p>
          <button
            type="button"
            title="新建文件夹"
            onClick={() => {
              setNewFolderOpen((v) => !v);
              setNewFolderName("");
            }}
            className="rounded-md p-1 text-muted transition hover:bg-surface-muted hover:text-brand"
          >
            <FolderPlus className="h-4 w-4" />
          </button>
        </div>

        {newFolderOpen && (
          <div className="mb-1 flex items-center gap-1 px-1">
            <input
              autoFocus
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitNewFolder();
                if (e.key === "Escape") setNewFolderOpen(false);
              }}
              placeholder="文件夹名称"
              className="h-8 flex-1 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-brand"
            />
            <button
              type="button"
              onClick={submitNewFolder}
              className="rounded-md p-1.5 text-brand hover:bg-brand-soft"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setNewFolderOpen(false)}
              className="rounded-md p-1.5 text-muted hover:bg-surface-muted"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="flex-1 space-y-0.5 overflow-y-auto">
          {folders.length === 0 && !newFolderOpen && (
            <p className="px-2 py-3 text-xs text-muted">暂无文件夹</p>
          )}
          {folders.map((f) =>
            renamingId === f.id ? (
              <div key={f.id} className="flex items-center gap-1 px-1">
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") renameFolder(f.id);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  className="h-8 flex-1 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-brand"
                />
                <button
                  type="button"
                  onClick={() => renameFolder(f.id)}
                  className="rounded-md p-1.5 text-brand hover:bg-brand-soft"
                >
                  <Check className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div
                key={f.id}
                className={cn(
                  "group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition",
                  activeFolder === f.id
                    ? "bg-brand-soft text-brand"
                    : "text-foreground hover:bg-surface-muted",
                )}
              >
                <button
                  type="button"
                  onClick={() => {
                    setScope("all");
                    setActiveFolder(activeFolder === f.id ? null : f.id);
                  }}
                  className="flex min-w-0 flex-1 items-center gap-2"
                >
                  <FolderIcon
                    className={cn("h-4 w-4 shrink-0", activeFolder === f.id ? "text-brand" : "text-muted")}
                  />
                  <span className="flex-1 truncate text-left">{f.name}</span>
                </button>
                <span className="text-xs text-muted group-hover:hidden">{f.count}</span>
                <div className="hidden group-hover:block">
                  <RowMenu
                    items={[
                      {
                        label: "重命名",
                        icon: Pencil,
                        onClick: () => {
                          setRenamingId(f.id);
                          setRenameValue(f.name);
                        },
                      },
                      { label: "删除", icon: Trash, danger: true, onClick: () => deleteFolder(f) },
                    ]}
                  />
                </div>
              </div>
            ),
          )}
        </div>

        <div className="mt-3 rounded-xl border border-border p-3">
          <p className="text-sm font-medium">团队存储空间</p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full bg-brand transition-all"
              style={{ width: `${Math.max(usedPct, storage && storage.usedBytes > 0 ? 2 : 0)}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-muted">
            {storage
              ? `${formatBytes(storage.usedBytes)} / ${formatBytes(storage.quotaBytes)} · ${storage.fileCount} 个文件`
              : "统计中…"}
          </p>
        </div>
      </aside>

      {/* right: tabs + grid */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-border px-6 py-3">
          <div className="flex items-center gap-1">
            {TYPE_TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setType(t.key)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition",
                  type === t.key
                    ? "bg-surface-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="relative ml-auto">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && loadAssets()}
              placeholder="输入关键词…"
              className="h-9 w-52 rounded-lg border border-border bg-surface pl-8 pr-3 text-sm outline-none focus:border-brand"
            />
          </div>

          {/* hidden pickers */}
          <input
            ref={fileRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              handleUpload(e.target.files, false);
              e.target.value = "";
            }}
          />
          <input
            ref={folderRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              handleUpload(e.target.files, true);
              e.target.value = "";
            }}
          />

          {!isTrash && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setUploadMenu((v) => !v)}
                disabled={uploading}
                className="brand-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-seal transition hover:opacity-90 disabled:opacity-60"
              >
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                上传
                <ChevronDown className="h-3.5 w-3.5 opacity-80" />
              </button>
              {uploadMenu && !uploading && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setUploadMenu(false)} />
                  <div className="absolute right-0 z-30 mt-1 w-36 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg">
                    <MenuItem
                      icon={FileUp}
                      label="上传文件"
                      onClick={() => {
                        setUploadMenu(false);
                        fileRef.current?.click();
                      }}
                    />
                    <MenuItem
                      icon={FolderUp}
                      label="上传文件夹"
                      onClick={() => {
                        setUploadMenu(false);
                        folderRef.current?.click();
                      }}
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {(uploading || activeFolder) && (
          <div className="flex items-center gap-2 border-b border-border bg-surface-muted/40 px-6 py-1.5 text-xs text-muted">
            {uploading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
                {uploadMsg || "上传中…"}
              </>
            ) : (
              <>
                <FolderIcon className="h-3.5 w-3.5 text-brand" />
                当前文件夹：{folders.find((f) => f.id === activeFolder)?.name ?? ""}
                <button
                  type="button"
                  onClick={() => setActiveFolder(null)}
                  className="ml-1 text-brand hover:underline"
                >
                  返回全部
                </button>
              </>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="py-20 text-center text-sm text-muted">加载中…</p>
          ) : assets.length === 0 ? (
            <p className="py-20 text-center text-sm text-muted">
              {isTrash ? "回收站是空的" : "暂无文件，点击「上传」添加文件或文件夹"}
            </p>
          ) : (
            ORDER.filter((b) => grouped[b]?.length).map((b) => (
              <section key={b} className="mb-7">
                <h3 className="mb-3 text-sm font-semibold text-foreground">{b}</h3>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
                  {grouped[b].map((a) => (
                    <FileCard
                      key={a.id}
                      asset={a}
                      trash={isTrash}
                      onRename={() => renameAsset(a)}
                      onTrash={() => trashAsset(a)}
                      onRestore={() => restoreAsset(a)}
                      onDeleteForever={() => deleteAssetForever(a)}
                    />
                  ))}
                </div>
              </section>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Scope({
  icon: Icon,
  label,
  count,
  active,
  onClick,
}: {
  icon: typeof Files;
  label: string;
  count: number;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition",
        active ? "bg-surface-muted font-medium text-foreground" : "text-muted-foreground hover:bg-surface-muted",
      )}
    >
      <Icon className={cn("h-[18px] w-[18px]", active ? "text-brand" : "text-muted")} />
      <span className="flex-1 text-left">{label}</span>
      <span className="text-xs text-muted">{count}</span>
    </button>
  );
}

type MenuAction = { label: string; icon: typeof Pencil; onClick: () => void; danger?: boolean };

function MenuItem({ icon: Icon, label, onClick, danger }: MenuAction) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition hover:bg-surface-muted",
        danger ? "text-red-600" : "text-foreground",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

/** Hover "⋯" button revealing a small action menu, with click-outside to close. */
function RowMenu({ items }: { items: MenuAction[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="rounded-md p-1 text-muted transition hover:bg-surface-muted hover:text-foreground"
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-20"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
            }}
          />
          <div className="absolute right-0 z-30 mt-1 w-32 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg">
            {items.map((it) => (
              <MenuItem
                key={it.label}
                {...it}
                onClick={() => {
                  setOpen(false);
                  it.onClick();
                }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function FileCard({
  asset,
  trash,
  onRename,
  onTrash,
  onRestore,
  onDeleteForever,
}: {
  asset: Asset;
  trash: boolean;
  onRename: () => void;
  onTrash: () => void;
  onRestore: () => void;
  onDeleteForever: () => void;
}) {
  const router = useRouter();
  const isMedia = ["VIDEO", "FINISHED", "AUDIO"].includes(asset.type);
  const open = () =>
    asset.isProject
      ? router.push(`/editor/${asset.id}`)
      : asset.url && window.open(asset.url, "_blank", "noopener");
  return (
    <div className="group cursor-pointer">
      <div
        className="relative aspect-video overflow-hidden rounded-xl border border-border"
        style={{ backgroundImage: tileGradient(asset.id) }}
        onClick={open}
      >
        {asset.thumbnailUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={asset.thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
        )}
        <span className="absolute left-2 top-2 rounded bg-black/40 px-1.5 py-0.5 text-[10px] text-white backdrop-blur">
          {TAG[asset.type] ?? "素材"}
        </span>

        {/* hover action menu —— 工程在云盘只读（管理在「合成量产」），不显示菜单 */}
        <div
          className={cn(
            "absolute right-1.5 top-1.5 opacity-0 transition group-hover:opacity-100",
            asset.isProject && "hidden",
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="rounded-md bg-black/40 backdrop-blur">
            {trash ? (
              <RowMenu
                items={[
                  { label: "恢复", icon: RotateCcw, onClick: onRestore },
                  { label: "彻底删除", icon: Trash, danger: true, onClick: onDeleteForever },
                ]}
              />
            ) : (
              <RowMenu
                items={[
                  { label: "重命名", icon: Pencil, onClick: onRename },
                  { label: "删除", icon: Trash, danger: true, onClick: onTrash },
                ]}
              />
            )}
          </div>
        </div>

        {isMedia && asset.url && (
          <span className="absolute inset-0 m-auto flex h-9 w-9 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur transition group-hover:opacity-100">
            <Play className="h-4 w-4 translate-x-0.5" fill="currentColor" />
          </span>
        )}
        {asset.durationSec != null && (
          <span className="absolute bottom-1.5 right-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[10px] text-white">
            {formatDuration(asset.durationSec)}
          </span>
        )}
      </div>
      <p className="mt-1.5 truncate text-sm font-medium text-foreground">{asset.name}</p>
      <p className="flex items-center gap-1.5 text-xs text-muted">
        <span>{formatDateTime(asset.createdAt)}</span>
        {asset.sizeBytes != null && asset.sizeBytes > 0 && (
          <>
            <span>·</span>
            <span>{formatBytes(asset.sizeBytes)}</span>
          </>
        )}
      </p>
    </div>
  );
}
