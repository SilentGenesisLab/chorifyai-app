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
import { GroupImporter, type ImportGroup, type ImportClip } from "./GroupImporter";

type Clip = ImportClip;
type Group = ImportGroup & { uploading?: number };
type ComboStatus = "idle" | "mixing" | "done" | "failed";
type Combo = { id: string; clips: Clip[]; status: ComboStatus; resultUrl?: string; localPath?: string };

const rid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

function shuffle<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

/** 片段缩略图：有首帧封面就用 <img>，否则回退到 <video> 取首帧。 */
function ClipThumb({ clip, className }: { clip: Clip; className?: string }) {
  return clip.thumbnailUrl ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={clip.thumbnailUrl} alt="" className={className} />
  ) : (
    <video src={clip.url} muted preload="metadata" className={className} />
  );
}

export function ComposeEditor({
  project,
}: {
  project: {
    id: string;
    name: string;
    width: number;
    height: number;
    config?: unknown;
  };
}) {
  const router = useRouter();
  const initialGroups = (() => {
    const g = (project.config as { groups?: Group[] } | null)?.groups;
    return Array.isArray(g) ? g : [];
  })();

  const [groups, setGroups] = useState<Group[]>(initialGroups);
  const [count, setCount] = useState(20);
  const [combos, setCombos] = useState<Combo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [composing, setComposing] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [folders, setFolders] = useState<{ id: string; name: string }[]>([]);
  const [saveFolderId, setSaveFolderId] = useState("");
  const [importerOpen, setImporterOpen] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/drive/folders")
      .then((r) => r.json())
      .then((d) => {
        if (d?.ok) setFolders(d.folders);
      })
      .catch(() => {});
  }, []);

  // 持久化：镜头分组变化时防抖保存到工程 config（跳过首次加载）
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    const anyUploading = groups.some((g) => (g.uploading ?? 0) > 0);
    if (anyUploading) return; // 等上传完再保存
    const t = setTimeout(() => {
      const clean = groups.map((g) => ({ id: g.id, name: g.name, clips: g.clips }));
      fetch(`/api/projects/${project.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ config: { groups: clean }, comboCount: combos.length }),
      })
        .then(() => {
          setSaved(true);
          setTimeout(() => setSaved(false), 1500);
        })
        .catch(() => {});
    }, 800);
    return () => clearTimeout(t);
  }, [groups, combos.length, project.id]);

  const removeGroup = (id: string) => setGroups((gs) => gs.filter((g) => g.id !== id));

  const readyGroups = groups.filter((g) => g.clips.length > 0);
  const anyUploading = groups.some((g) => (g.uploading ?? 0) > 0);

  function generate() {
    if (!readyGroups.length) return;
    const out: Combo[] = [];
    const seen = new Set<string>();
    const maxPossible = readyGroups.reduce((total, group) => total * Math.max(1, group.clips.length), 1);
    const target = Math.min(count, maxPossible);
    const shuffledGroups = readyGroups.map((group) => ({ ...group, clips: shuffle(group.clips) }));
    let guard = 0;
    while (out.length < target && guard < target * 30) {
      const clips = shuffledGroups.map((g, groupIndex) => {
        const offset = out.length + groupIndex * 3 + Math.floor(out.length / Math.max(1, g.clips.length));
        return g.clips[offset % g.clips.length];
      });
      const signature = clips.map((clip) => clip.url).join("|");
      guard += 1;
      if (seen.has(signature)) {
        const fallback = readyGroups.map((g) => g.clips[Math.floor(Math.random() * g.clips.length)]);
        const fallbackSignature = fallback.map((clip) => clip.url).join("|");
        if (seen.has(fallbackSignature)) continue;
        seen.add(fallbackSignature);
        out.push({ id: rid(), clips: fallback, status: "idle" });
        continue;
      }
      seen.add(signature);
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
                cs.map((x) =>
                  x.id === c.id
                    ? { ...x, status: "done", resultUrl: st.url, localPath: st.localPath }
                    : x,
                ),
              );
              fetch("/api/drive/assets", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({
                  name: `${project.name}_成片${idx + 1}.mp4`,
                  type: "finished",
                  url: st.url,
                  thumbnailUrl: st.thumbnailUrl ?? undefined,
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
    <div className="flex h-screen flex-col bg-surface text-foreground">
      {/* 顶栏 */}
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
        <button
          type="button"
          onClick={() => router.push("/compose")}
          className="text-muted-foreground transition hover:text-foreground"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="font-display text-lg font-bold tracking-tight text-foreground">
          {BRAND.name}
        </span>
        <span className="max-w-[220px] truncate text-sm text-muted">/ {project.name}</span>
        <span className="rounded bg-surface-muted px-2 py-0.5 text-xs text-muted-foreground">
          {project.width}×{project.height}
        </span>
        {saved && <span className="text-xs text-jade">已保存</span>}

        <div className="ml-auto flex items-center gap-2.5">
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
            产出数量
            <input
              type="number"
              min={1}
              max={200}
              value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
              className="w-16 rounded-lg border border-border bg-surface px-2 py-1.5 text-center text-sm text-foreground outline-none focus:border-brand/50"
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
        <aside className="flex w-72 shrink-0 flex-col border-r border-border">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              <Layers className="h-4 w-4 text-brand" />
              镜头分组
            </span>
            <span className="text-xs text-muted">{readyGroups.length} 组</span>
          </div>
          <p className="px-4 pb-2 text-xs leading-relaxed text-muted">
            上传文件夹 = 一个镜头分组；生成时按分组顺序，每组随机抽一条拼接成片。
          </p>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3">
            {groups.length === 0 ? (
              <button
                type="button"
                onClick={() => setImporterOpen(true)}
                className="flex h-36 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong text-muted transition hover:border-brand/50 hover:text-brand"
              >
                <FolderPlus className="h-7 w-7" />
                <span className="text-sm">添加镜头分组</span>
              </button>
            ) : (
              groups.map((g, i) => (
                <div key={g.id} className="ink-card p-2.5">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="flex h-5 min-w-5 items-center justify-center rounded bg-brand px-1 text-[11px] font-bold text-white">
                      {i + 1}
                    </span>
                    <span className="flex-1 truncate text-sm font-medium text-foreground">
                      {g.name}
                    </span>
                    {(g.uploading ?? 0) > 0 ? (
                      <span className="flex items-center gap-1 text-xs text-muted">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {g.uploading}
                      </span>
                    ) : (
                      <span className="text-xs text-muted">{g.clips.length} 条</span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeGroup(g.id)}
                      className="text-muted transition hover:text-brand"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="flex gap-1.5 overflow-x-auto">
                    {g.clips.slice(0, 6).map((c, ci) => (
                      <div
                        key={ci}
                        className="relative h-12 w-9 shrink-0 overflow-hidden rounded bg-surface-muted"
                      >
                        <ClipThumb clip={c} className="h-full w-full object-cover" />
                      </div>
                    ))}
                    {g.clips.length > 6 && (
                      <span className="flex h-12 w-9 shrink-0 items-center justify-center rounded bg-surface-muted text-[11px] text-muted">
                        +{g.clips.length - 6}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="border-t border-border p-3">
            <button
              type="button"
              onClick={() => setImporterOpen(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-medium text-foreground transition hover:bg-surface-muted"
            >
              <FolderPlus className="h-4 w-4" />
              添加镜头分组
            </button>
          </div>
        </aside>

        {/* 右：视频组合 */}
        <main className="flex min-h-0 flex-1 flex-col bg-background">
          {combos.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted">
              <Film className="h-10 w-10 text-border-strong" />
              <p className="text-sm">
                {readyGroups.length
                  ? "点右上角「生成视频」开始随机组合"
                  : anyUploading
                    ? "素材上传中…"
                    : "先在左侧添加镜头分组（每个文件夹一个镜头分组）"}
              </p>
            </div>
          ) : (
            <>
              <div className="flex shrink-0 items-center gap-3 border-b border-border bg-surface/70 px-5 py-2.5 text-sm">
                <label className="flex items-center gap-2 text-foreground">
                  <input
                    type="checkbox"
                    checked={selected.size === combos.length && combos.length > 0}
                    onChange={toggleAll}
                    className="h-4 w-4 accent-[var(--color-brand)]"
                  />
                  全选
                </label>
                <span className="text-muted">
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

              <div className="min-h-0 flex-1 overflow-auto p-5">
                <table className="w-full border-separate border-spacing-y-2">
                  <thead>
                    <tr className="text-left text-xs text-muted">
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
                      <tr key={c.id} className="bg-surface">
                        <td className="rounded-l-lg border-y border-l border-border px-2">
                          <input
                            type="checkbox"
                            checked={selected.has(c.id)}
                            onChange={() => toggle(c.id)}
                            className="h-4 w-4 accent-[var(--color-brand)]"
                          />
                        </td>
                        <td className="border-y border-border px-2 text-sm text-muted">#{ri + 1}</td>
                        {c.clips.map((cl, ci) => (
                          <td key={ci} className="border-y border-border px-2 py-1.5">
                            <div className="flex items-center gap-2">
                              <div className="relative h-14 w-10 shrink-0 overflow-hidden rounded bg-surface-muted">
                                <ClipThumb clip={cl} className="h-full w-full object-cover" />
                              </div>
                              <span className="max-w-[90px] truncate text-[11px] text-muted">
                                {cl.name}
                              </span>
                            </div>
                          </td>
                        ))}
                        <td className="rounded-r-lg border-y border-r border-border px-2">
                          {c.status === "mixing" ? (
                            <span className="flex items-center gap-1.5 text-xs text-amber-600">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              合成中…
                            </span>
                          ) : c.status === "done" && c.resultUrl ? (
                            <div className="flex items-center gap-2">
                              <a
                                href={c.resultUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1 rounded bg-jade/15 px-2 py-1 text-xs text-jade transition hover:bg-jade/25"
                              >
                                <Play className="h-3 w-3" />
                                播放
                              </a>
                              <a
                                href={c.resultUrl}
                                download
                                className="text-muted transition hover:text-foreground"
                              >
                                <Download className="h-3.5 w-3.5" />
                              </a>
                              {c.localPath && (
                                <span className="max-w-[120px] truncate text-[10px] text-muted" title={c.localPath}>
                                  {c.localPath}
                                </span>
                              )}
                            </div>
                          ) : c.status === "failed" ? (
                            <span className="text-xs text-brand">合成失败</span>
                          ) : (
                            <span className="text-xs text-muted">待合成</span>
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
            className="absolute inset-0 bg-ink/40"
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

      <GroupImporter
        open={importerOpen}
        onClose={() => setImporterOpen(false)}
        onConfirm={(gs) => setGroups((prev) => [...prev, ...gs])}
      />
    </div>
  );
}
