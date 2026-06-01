"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  FolderPlus,
  Loader2,
  Rocket,
  Film,
  Trash2,
  Play,
  Download,
  X,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { uploadFile } from "@/lib/upload";

type Clip = { url: string; name: string };
type Group = { id: string; name: string; clips: Clip[]; uploading?: number };
type ComboStatus = "idle" | "mixing" | "done" | "failed";
type Combo = { id: string; clips: Clip[]; status: ComboStatus; resultUrl?: string };

const rid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);
const VIDEO_RE = /\.(mp4|mov|webm|mkv|avi|m4v)$/i;

export function ComposeEditor({
  project,
}: {
  project: { id: string; name: string; width: number; height: number };
}) {
  const router = useRouter();
  const [groups, setGroups] = useState<Group[]>([]);
  const [count, setCount] = useState(20);
  const [combos, setCombos] = useState<Combo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [composing, setComposing] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [folders, setFolders] = useState<{ id: string; name: string }[]>([]);
  const [saveFolderId, setSaveFolderId] = useState("");
  const folderRef = useRef<HTMLInputElement>(null);

  // webkitdirectory 是非标准属性，用 ref 设置
  useEffect(() => {
    const el = folderRef.current;
    if (el) {
      el.setAttribute("webkitdirectory", "");
      el.setAttribute("directory", "");
    }
  }, []);

  useEffect(() => {
    fetch("/api/drive/folders")
      .then((r) => r.json())
      .then((d) => {
        if (d?.ok) setFolders(d.folders);
      })
      .catch(() => {});
  }, []);

  // 上传一个文件夹 → 新建一个镜头分组，逐个上传到 OSS
  async function onFolderPick(e: React.ChangeEvent<HTMLInputElement>) {
    const all = Array.from(e.target.files ?? []);
    e.target.value = "";
    const files = all.filter((f) => f.type.startsWith("video/") || VIDEO_RE.test(f.name));
    if (!files.length) return;
    const first = files[0] as File & { webkitRelativePath?: string };
    const folderName = first.webkitRelativePath?.split("/")[0] || `分组${groups.length + 1}`;
    const gid = rid();
    setGroups((gs) => [...gs, { id: gid, name: folderName, clips: [], uploading: files.length }]);
    for (const f of files) {
      try {
        const up = await uploadFile(f, "video");
        setGroups((gs) =>
          gs.map((g) =>
            g.id === gid
              ? { ...g, clips: [...g.clips, { url: up.url, name: f.name }], uploading: (g.uploading ?? 1) - 1 }
              : g,
          ),
        );
      } catch {
        setGroups((gs) =>
          gs.map((g) => (g.id === gid ? { ...g, uploading: (g.uploading ?? 1) - 1 } : g)),
        );
      }
    }
  }

  const removeGroup = (id: string) => setGroups((gs) => gs.filter((g) => g.id !== id));

  const readyGroups = groups.filter((g) => g.clips.length > 0);
  const anyUploading = groups.some((g) => (g.uploading ?? 0) > 0);

  // 生成视频 = 随机组合：每个分组按顺序各随机抽 1 条，组合 count 次
  function generate() {
    if (!readyGroups.length) return;
    const out: Combo[] = [];
    for (let i = 0; i < count; i++) {
      const clips = readyGroups.map((g) => g.clips[Math.floor(Math.random() * g.clips.length)]);
      out.push({ id: rid(), clips, status: "idle" });
    }
    setCombos(out);
    setSelected(new Set());
  }

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const toggleAll = () =>
    setSelected((s) => (s.size === combos.length ? new Set() : new Set(combos.map((c) => c.id))));

  // 合成选中的组合：逐条调 /api/mix（ffmpeg 拼接→OSS），完成后存入云盘成片
  async function composeSelected() {
    const targets = combos.filter((c) => selected.has(c.id) && c.status !== "done");
    setSaveOpen(false);
    if (!targets.length) return;
    setComposing(true);
    await Promise.all(
      targets.map(async (c, idx) => {
        setCombos((cs) => cs.map((x) => (x.id === c.id ? { ...x, status: "mixing" } : x)));
        try {
          const start = await fetch("/api/mix", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              clips: c.clips.map((cl) => cl.url),
              width: project.width,
              height: project.height,
            }),
          }).then((r) => r.json());
          if (!start?.job_id) throw new Error("启动失败");
          for (let i = 0; i < 240; i++) {
            await new Promise((r) => setTimeout(r, 2000));
            const st = await fetch(`/api/mix/${start.job_id}`).then((r) => r.json());
            if (st.status === "done") {
              setCombos((cs) =>
                cs.map((x) => (x.id === c.id ? { ...x, status: "done", resultUrl: st.url } : x)),
              );
              fetch("/api/drive/assets", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({
                  name: `${project.name}_成片${idx + 1}.mp4`,
                  type: "finished",
                  url: st.url,
                  folderId: saveFolderId || undefined,
                }),
              }).catch(() => {});
              return;
            }
            if (st.status === "failed") {
              setCombos((cs) => cs.map((x) => (x.id === c.id ? { ...x, status: "failed" } : x)));
              return;
            }
          }
          setCombos((cs) => cs.map((x) => (x.id === c.id ? { ...x, status: "failed" } : x)));
        } catch {
          setCombos((cs) => cs.map((x) => (x.id === c.id ? { ...x, status: "failed" } : x)));
        }
      }),
    );
    setComposing(false);
  }

  const doneCount = combos.filter((c) => c.status === "done").length;

  return (
    <div className="flex h-screen flex-col bg-[#0d0d11] text-white/90">
      {/* 顶栏 */}
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-white/10 px-4">
        <button
          type="button"
          onClick={() => router.push("/compose")}
          className="text-white/70 transition hover:text-white"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="font-display text-lg font-bold tracking-tight text-white">{BRAND.name}</span>
        <span className="max-w-[220px] truncate text-sm text-white/45">/ {project.name}</span>
        <span className="rounded bg-white/10 px-2 py-0.5 text-xs text-white/60">
          {project.width}×{project.height}
        </span>

        <div className="ml-auto flex items-center gap-2.5">
          <label className="flex items-center gap-1.5 text-sm text-white/60">
            产出数量
            <input
              type="number"
              min={1}
              max={200}
              value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
              className="w-16 rounded-lg border border-white/15 bg-white/5 px-2 py-1.5 text-center text-sm text-white outline-none focus:border-brand/50"
            />
          </label>
          <button
            type="button"
            onClick={generate}
            disabled={!readyGroups.length}
            className="brand-gradient flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-40"
          >
            <Rocket className="h-4 w-4" />
            生成视频
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* 左：镜头分组 */}
        <aside className="flex w-72 shrink-0 flex-col border-r border-white/10">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              <Layers className="h-4 w-4 text-brand" />
              镜头分组
            </span>
            <span className="text-xs text-white/40">{readyGroups.length} 组</span>
          </div>
          <p className="px-4 pb-2 text-xs leading-relaxed text-white/35">
            上传文件夹 = 一个镜头分组；生成时按分组顺序，每组随机抽一条拼接成片。
          </p>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3">
            {groups.length === 0 ? (
              <button
                type="button"
                onClick={() => folderRef.current?.click()}
                className="flex h-36 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 text-white/45 transition hover:border-white/30 hover:text-white/70"
              >
                <FolderPlus className="h-7 w-7" />
                <span className="text-sm">上传文件夹</span>
              </button>
            ) : (
              groups.map((g, i) => (
                <div key={g.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-2.5">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="flex h-5 min-w-5 items-center justify-center rounded bg-brand/80 px-1 text-[11px] font-bold text-white">
                      {i + 1}
                    </span>
                    <span className="flex-1 truncate text-sm font-medium">{g.name}</span>
                    {(g.uploading ?? 0) > 0 ? (
                      <span className="flex items-center gap-1 text-xs text-white/45">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {g.uploading}
                      </span>
                    ) : (
                      <span className="text-xs text-white/45">{g.clips.length} 条</span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeGroup(g.id)}
                      className="text-white/40 transition hover:text-rose-400"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="flex gap-1.5 overflow-x-auto">
                    {g.clips.slice(0, 6).map((c, ci) => (
                      <div
                        key={ci}
                        className="relative h-12 w-9 shrink-0 overflow-hidden rounded bg-black/40"
                      >
                        <video src={c.url} muted preload="metadata" className="h-full w-full object-cover" />
                      </div>
                    ))}
                    {g.clips.length > 6 && (
                      <span className="flex h-12 w-9 shrink-0 items-center justify-center rounded bg-white/5 text-[11px] text-white/50">
                        +{g.clips.length - 6}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="border-t border-white/10 p-3">
            <button
              type="button"
              onClick={() => folderRef.current?.click()}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-white/15"
            >
              <FolderPlus className="h-4 w-4" />
              上传文件夹
            </button>
          </div>
          <input ref={folderRef} type="file" multiple hidden onChange={onFolderPick} />
        </aside>

        {/* 右：视频组合 */}
        <main className="flex min-h-0 flex-1 flex-col">
          {combos.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-white/40">
              <Film className="h-10 w-10 text-white/20" />
              <p className="text-sm">
                {readyGroups.length
                  ? "点右上角「生成视频」开始随机组合"
                  : anyUploading
                    ? "素材上传中…"
                    : "先在左侧上传文件夹（每个文件夹一个镜头分组）"}
              </p>
            </div>
          ) : (
            <>
              {/* 工具条 */}
              <div className="flex shrink-0 items-center gap-3 border-b border-white/10 px-5 py-2.5 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selected.size === combos.length && combos.length > 0}
                    onChange={toggleAll}
                    className="h-4 w-4 accent-[var(--color-brand)]"
                  />
                  全选
                </label>
                <span className="text-white/45">
                  共 {combos.length} 个组合 · 已选 {selected.size}
                  {doneCount > 0 && ` · 已合成 ${doneCount}`}
                </span>
                <button
                  type="button"
                  onClick={() => setSaveOpen(true)}
                  disabled={!selected.size || composing}
                  className="ml-auto flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-fuchsia-600 px-4 py-1.5 font-medium text-white transition hover:opacity-90 disabled:opacity-40"
                >
                  {composing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Layers className="h-4 w-4" />}
                  瀑布流合成
                </button>
              </div>

              {/* 组合表：列=镜头分组，行=一个组合 */}
              <div className="min-h-0 flex-1 overflow-auto p-5">
                <table className="w-full border-separate border-spacing-y-2">
                  <thead>
                    <tr className="text-left text-xs text-white/45">
                      <th className="w-10 px-2"></th>
                      <th className="w-14 px-2">序号</th>
                      {readyGroups.map((g, i) => (
                        <th key={g.id} className="px-2 font-medium">
                          {i + 1}.{g.name}
                        </th>
                      ))}
                      <th className="w-32 px-2">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {combos.map((c, ri) => (
                      <tr key={c.id} className="rounded-lg bg-white/[0.03]">
                        <td className="px-2">
                          <input
                            type="checkbox"
                            checked={selected.has(c.id)}
                            onChange={() => toggle(c.id)}
                            className="h-4 w-4 accent-[var(--color-brand)]"
                          />
                        </td>
                        <td className="px-2 text-sm text-white/60">#{ri + 1}</td>
                        {c.clips.map((cl, ci) => (
                          <td key={ci} className="px-2 py-1.5">
                            <div className="flex items-center gap-2">
                              <div className="relative h-14 w-10 shrink-0 overflow-hidden rounded bg-black/40">
                                <video
                                  src={cl.url}
                                  muted
                                  preload="metadata"
                                  className="h-full w-full object-cover"
                                />
                              </div>
                              <span className="max-w-[90px] truncate text-[11px] text-white/55">
                                {cl.name}
                              </span>
                            </div>
                          </td>
                        ))}
                        <td className="px-2">
                          {c.status === "mixing" ? (
                            <span className="flex items-center gap-1.5 text-xs text-amber-300">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              合成中…
                            </span>
                          ) : c.status === "done" && c.resultUrl ? (
                            <div className="flex items-center gap-2">
                              <a
                                href={c.resultUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-1 text-xs text-emerald-300 transition hover:bg-emerald-500/30"
                              >
                                <Play className="h-3 w-3" />
                                播放
                              </a>
                              <a
                                href={c.resultUrl}
                                download
                                className="text-white/50 transition hover:text-white"
                              >
                                <Download className="h-3.5 w-3.5" />
                              </a>
                            </div>
                          ) : c.status === "failed" ? (
                            <span className="text-xs text-rose-400">合成失败</span>
                          ) : (
                            <span className="text-xs text-white/35">待合成</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </main>
      </div>

      {/* 保存位置弹窗 */}
      {saveOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setSaveOpen(false)}
            className="absolute inset-0 bg-black/50"
          />
          <div className="relative z-10 w-full max-w-md rounded-2xl bg-surface p-6 text-foreground shadow-xl">
            <div className="mb-1 flex items-center justify-between">
              <h3 className="font-display text-lg font-bold">合成并保存到</h3>
              <button type="button" onClick={() => setSaveOpen(false)} className="text-muted hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">
              已选 {selected.size} 条，合成后保存到云盘（OSS），可在「云盘」对应位置查看。
            </p>
            <label className="mb-1.5 block text-sm font-medium">保存位置</label>
            <select
              value={saveFolderId}
              onChange={(e) => setSaveFolderId(e.target.value)}
              className="mb-5 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-brand/50"
            >
              <option value="">云盘根目录</option>
              {folders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSaveOpen(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm transition hover:bg-surface-muted"
              >
                取消
              </button>
              <button
                type="button"
                onClick={composeSelected}
                className="brand-gradient rounded-lg px-5 py-2 text-sm font-semibold text-white shadow-seal transition hover:opacity-90"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
