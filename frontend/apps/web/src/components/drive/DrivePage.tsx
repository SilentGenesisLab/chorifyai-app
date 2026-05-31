"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Files,
  User,
  Trash2,
  Folder as FolderIcon,
  Search,
  Upload,
  Loader2,
  Play,
} from "lucide-react";
import { cn, formatDateTime, formatDuration } from "@/lib/utils";
import { tileGradient } from "@/components/material/types";
import { uploadFile, type UploadKind } from "@/lib/upload";

type Folder = { id: string; name: string; count: number };
type Asset = {
  id: string;
  name: string;
  type: string;
  url?: string | null;
  thumbnailUrl?: string | null;
  durationSec?: number | null;
  folderId?: string | null;
  createdAt: string;
};

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

export function DrivePage() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadFolders = useCallback(async () => {
    const r = await fetch("/api/drive/folders");
    const d = await r.json();
    if (d.ok) setFolders(d.folders);
  }, []);

  const loadAssets = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (type !== "all") p.set("type", type);
      if (activeFolder) p.set("folderId", activeFolder);
      if (q.trim()) p.set("q", q.trim());
      const r = await fetch(`/api/drive/assets?${p.toString()}`);
      const d = await r.json();
      if (d.ok) setAssets(d.assets);
    } finally {
      setLoading(false);
    }
  }, [type, activeFolder, q]);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);
  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  const grouped = useMemo(() => {
    const g: Record<string, Asset[]> = {};
    for (const a of assets) {
      const b = bucketOf(a.createdAt);
      (g[b] ??= []).push(a);
    }
    return g;
  }, [assets]);

  async function onFiles(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        const kind: UploadKind = f.type.startsWith("video")
          ? "video"
          : f.type.startsWith("audio")
            ? "audio"
            : f.type.startsWith("image")
              ? "image"
              : "file";
        const up = await uploadFile(f, kind);
        await fetch("/api/drive/assets", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            name: up.name,
            type: kind === "file" ? "material" : kind,
            url: up.url,
            folderId: activeFolder,
          }),
        });
      }
      await Promise.all([loadAssets(), loadFolders()]);
    } catch (e) {
      alert(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex h-full min-h-0">
      {/* left: scopes + folders + storage */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-border p-4">
        <div className="space-y-0.5">
          <Scope icon={Files} label="全部文件" count={assets.length} active onClick={() => setActiveFolder(null)} />
          <Scope icon={User} label="我创建的" count={assets.length} onClick={() => setActiveFolder(null)} />
          <Scope icon={Trash2} label="回收站" count={0} onClick={() => {}} />
        </div>
        <div className="ink-rule my-4" />
        <p className="mb-2 px-1 text-sm text-muted">全部文件夹</p>
        <div className="flex-1 space-y-0.5 overflow-y-auto">
          {folders.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setActiveFolder(activeFolder === f.id ? null : f.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition",
                activeFolder === f.id
                  ? "bg-brand-soft text-brand"
                  : "text-foreground hover:bg-surface-muted",
              )}
            >
              <FolderIcon className={cn("h-4 w-4", activeFolder === f.id ? "text-brand" : "text-muted")} />
              <span className="flex-1 truncate text-left">{f.name}</span>
              <span className="text-xs text-muted">{f.count}</span>
            </button>
          ))}
        </div>
        <div className="mt-3 rounded-xl border border-border p-3">
          <p className="text-sm font-medium">团队存储空间</p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
            <div className="h-full w-[7%] rounded-full bg-brand" />
          </div>
          <p className="mt-1.5 text-xs text-muted">36.5G / 512G · 剩余约 476G</p>
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
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="video/*,image/*,audio/*"
            className="hidden"
            onChange={(e) => onFiles(e.target.files)}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="brand-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-seal transition hover:opacity-90 disabled:opacity-60"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            上传
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="py-20 text-center text-sm text-muted">加载中…</p>
          ) : assets.length === 0 ? (
            <p className="py-20 text-center text-sm text-muted">暂无文件，点击「上传」添加</p>
          ) : (
            ORDER.filter((b) => grouped[b]?.length).map((b) => (
              <section key={b} className="mb-7">
                <h3 className="mb-3 text-sm font-semibold text-foreground">{b}</h3>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
                  {grouped[b].map((a) => (
                    <FileCard key={a.id} asset={a} />
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

function FileCard({ asset }: { asset: Asset }) {
  const isMedia = ["VIDEO", "FINISHED"].includes(asset.type);
  return (
    <div className="group cursor-pointer">
      <div
        className="relative aspect-video overflow-hidden rounded-xl border border-border"
        style={{ backgroundImage: tileGradient(asset.id) }}
      >
        {asset.thumbnailUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={asset.thumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
        )}
        <span className="absolute left-2 top-2 rounded bg-black/40 px-1.5 py-0.5 text-[10px] text-white backdrop-blur">
          {TAG[asset.type] ?? "素材"}
        </span>
        {isMedia && (
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
      <p className="text-xs text-muted">{formatDateTime(asset.createdAt)}</p>
    </div>
  );
}
