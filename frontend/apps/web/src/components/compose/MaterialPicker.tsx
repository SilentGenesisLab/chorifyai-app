"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X, Search, Upload, Loader2, Check, Folder as FolderIcon } from "lucide-react";
import { cn, formatDuration } from "@/lib/utils";
import { tileGradient } from "@/components/material/types";
import { uploadFile, type UploadKind } from "@/lib/upload";
import { Dropdown } from "@/components/material/Dropdown";

type Folder = { id: string; name: string; count: number };
export type PickedAsset = {
  id: string;
  name: string;
  type: string;
  url?: string | null;
  thumbnailUrl?: string | null;
  durationSec?: number | null;
  folderId?: string | null;
  createdAt: string;
};

const TABS = ["导入", "上传", "引用创意工程", "素材市场", "音频库", "数字人"];
const TYPE_OPTS = [
  { value: "all", label: "视频,图片,音频" },
  { value: "video", label: "视频" },
  { value: "image", label: "图片" },
  { value: "audio", label: "音频" },
];

export function MaterialPicker({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (assets: PickedAsset[]) => void;
}) {
  const [tab, setTab] = useState("导入");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [assets, setAssets] = useState<PickedAsset[]>([]);
  const [typeFilter, setTypeFilter] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Record<string, PickedAsset>>({});
  const [loading, setLoading] = useState(false);
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
      if (typeFilter !== "all") p.set("type", typeFilter);
      if (activeFolder) p.set("folderId", activeFolder);
      if (q.trim()) p.set("q", q.trim());
      const r = await fetch(`/api/drive/assets?${p.toString()}`);
      const d = await r.json();
      if (d.ok) setAssets(d.assets);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, activeFolder, q]);

  useEffect(() => {
    if (open) {
      loadFolders();
      loadAssets();
    }
  }, [open, loadFolders, loadAssets]);

  if (!open) return null;

  const selectedList = Object.values(selected);
  const toggle = (a: PickedAsset) =>
    setSelected((s) => {
      const n = { ...s };
      if (n[a.id]) delete n[a.id];
      else n[a.id] = a;
      return n;
    });

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
        const atype = kind === "file" ? "material" : kind;
        await fetch("/api/drive/assets", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            name: up.name,
            type: atype,
            url: up.url,
            folderId: activeFolder,
          }),
        });
      }
      setTab("导入");
      await Promise.all([loadAssets(), loadFolders()]);
    } catch (e) {
      alert(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
      <div className="flex h-full w-[1100px] max-w-[94vw] flex-col bg-surface text-foreground">
        {/* tabs */}
        <div className="flex items-center gap-6 border-b border-border px-6 py-3.5">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "relative py-1 text-[15px] font-medium transition",
                tab === t ? "text-brand" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
              {tab === t && (
                <span className="absolute inset-x-0 -bottom-[15px] h-0.5 rounded-full bg-brand" />
              )}
            </button>
          ))}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto text-muted transition hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* body */}
        {tab === "上传" ? (
          <div className="flex flex-1 items-center justify-center p-8">
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
              className="flex aspect-video w-full max-w-2xl flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-strong bg-surface/60 transition hover:border-brand/50 hover:bg-brand-soft/30"
            >
              {uploading ? (
                <Loader2 className="h-8 w-8 animate-spin text-brand" />
              ) : (
                <span className="flex h-14 w-14 items-center justify-center rounded-full bg-surface-muted text-muted">
                  <Upload className="h-7 w-7" />
                </span>
              )}
              <span className="text-[15px] font-medium">
                {uploading ? "上传中…" : "点击上传 视频 / 图片 / 音频"}
              </span>
              <span className="text-xs text-muted">
                上传到云盘（阿里云 OSS）{activeFolder ? "· 当前文件夹" : ""}
              </span>
            </button>
          </div>
        ) : tab === "导入" ? (
          <div className="flex min-h-0 flex-1">
            {/* folders */}
            <aside className="w-52 shrink-0 overflow-y-auto border-r border-border p-4">
              <p className="mb-2 text-sm font-medium">主题分类</p>
              <div className="relative mb-3">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && loadAssets()}
                  placeholder="输入关键词搜索"
                  className="h-8 w-full rounded-lg border border-border bg-surface pl-7 pr-2 text-xs outline-none focus:border-brand"
                />
              </div>
              <FolderItem
                label="全部"
                active={!activeFolder}
                onClick={() => setActiveFolder(null)}
              />
              {folders.map((f) => (
                <FolderItem
                  key={f.id}
                  label={f.name}
                  count={f.count}
                  active={activeFolder === f.id}
                  onClick={() => setActiveFolder(f.id)}
                />
              ))}
            </aside>

            {/* grid */}
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex items-center gap-3 border-b border-border px-5 py-2.5">
                <Dropdown
                  value={TYPE_OPTS.find((o) => o.value === typeFilter)?.label ?? "全部"}
                  options={TYPE_OPTS}
                  onChange={setTypeFilter}
                />
                <span className="ml-auto text-xs text-muted">共 {assets.length} 条</span>
              </div>
              {loading ? (
                <p className="py-20 text-center text-sm text-muted">加载中…</p>
              ) : assets.length === 0 ? (
                <p className="py-20 text-center text-sm text-muted">该分类暂无素材</p>
              ) : (
                <div className="grid grid-cols-2 content-start gap-4 overflow-y-auto p-5 sm:grid-cols-3 lg:grid-cols-4">
                  {assets.map((a) => (
                    <AssetCard
                      key={a.id}
                      asset={a}
                      selected={!!selected[a.id]}
                      onClick={() => toggle(a)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted">
            「{tab}」即将支持
          </div>
        )}

        {/* footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-3">
          <span className="mr-auto text-sm text-muted">已选 {selectedList.length} 个</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border bg-surface px-5 py-2 text-sm transition hover:bg-surface-muted"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(selectedList)}
            disabled={!selectedList.length}
            className="brand-gradient rounded-lg px-6 py-2 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-50"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

function FolderItem({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition",
        active
          ? "bg-brand-soft text-brand"
          : "text-foreground hover:bg-surface-muted",
      )}
    >
      <FolderIcon className={cn("h-4 w-4", active ? "text-brand" : "text-muted")} />
      <span className="flex-1 truncate text-left">{label}</span>
      {count != null && <span className="text-xs text-muted">{count}</span>}
    </button>
  );
}

function AssetCard({
  asset,
  selected,
  onClick,
}: {
  asset: PickedAsset;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="group text-left">
      <div
        className={cn(
          "relative aspect-[4/3] overflow-hidden rounded-xl border-2 transition",
          selected ? "border-brand" : "border-border group-hover:border-border-strong",
        )}
        style={{ backgroundImage: tileGradient(asset.id) }}
      >
        {asset.thumbnailUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={asset.thumbnailUrl}
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
          />
        )}
        {asset.durationSec != null && (
          <span className="absolute bottom-1.5 right-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[10px] text-white">
            {formatDuration(asset.durationSec)}
          </span>
        )}
        <span
          className={cn(
            "absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full border-2 transition",
            selected
              ? "border-brand bg-brand text-white"
              : "border-white/70 bg-black/20",
          )}
        >
          {selected && <Check className="h-3 w-3" />}
        </span>
      </div>
      <p className="mt-1.5 truncate text-xs text-foreground">{asset.name}</p>
    </button>
  );
}
