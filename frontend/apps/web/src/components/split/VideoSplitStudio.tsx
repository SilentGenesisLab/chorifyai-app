"use client";

import { useCallback, useRef, useState } from "react";
import {
  Film,
  Volume2,
  Clock,
  Plus,
  RotateCcw,
  ChevronLeft,
  Loader2,
  Check,
  Play,
  Download,
  Scissors,
  type LucideIcon,
} from "lucide-react";
import { uploadFile } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Method = "scene" | "speech" | "time";
type Status = "uploading" | "splitting" | "done" | "error";

type Clip = {
  index: number;
  start: number;
  end: number;
  duration: number;
  url?: string | null;
  thumbnail?: string | null;
};

type Video = {
  id: string;
  name: string;
  url: string;
  status: Status;
  clips: Clip[];
  error?: string;
};

const METHODS: {
  key: Method;
  title: string;
  desc: string;
  grad: string;
  icon: LucideIcon;
}[] = [
  { key: "scene", title: "按画面拆分", desc: "AI 识别画面切换，自动分镜", grad: "linear-gradient(135deg,#2563eb,#1e3a8a)", icon: Film },
  { key: "speech", title: "按口播拆分", desc: "按语音段落智能切分", grad: "linear-gradient(135deg,#7c3aed,#a21caf)", icon: Volume2 },
  { key: "time", title: "按时间拆分", desc: "按固定时长均匀切片", grad: "linear-gradient(135deg,#be123c,#3730a3)", icon: Clock },
];
const METHOD_LABEL: Record<Method, string> = {
  scene: "按画面拆分",
  speech: "按口播拆分",
  time: "按时间拆分",
};

const fmt = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};
const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

export function VideoSplitStudio() {
  const [view, setView] = useState<"select" | "work">("select");
  const [method, setMethod] = useState<Method>("scene");
  const [videos, setVideos] = useState<Video[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const active = videos.find((v) => v.id === activeId) ?? null;
  const patch = (id: string, p: Partial<Video>) =>
    setVideos((vs) => vs.map((v) => (v.id === id ? { ...v, ...p } : v)));

  const runSplit = useCallback(
    async (id: string, url: string, m: Method) => {
      patch(id, { status: "splitting", error: undefined });
      try {
        const res = await fetch("/api/split", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, method: m }),
        });
        // 后端异常可能返回纯文本（非 JSON），安全解析避免 "Unexpected token"。
        let data: { detail?: string; error?: string; clips?: Clip[] } | null = null;
        try {
          data = await res.json();
        } catch {
          /* non-JSON body */
        }
        if (!res.ok) throw new Error(data?.detail || data?.error || `拆分失败（HTTP ${res.status}）`);
        patch(id, { status: "done", clips: data?.clips ?? [] });
      } catch (e) {
        patch(id, { status: "error", error: e instanceof Error ? e.message : "拆分失败" });
      }
    },
    [],
  );

  const addVideo = useCallback(
    async (file: File) => {
      const id = uid();
      const video: Video = { id, name: file.name, url: "", status: "uploading", clips: [] };
      setVideos((vs) => [video, ...vs]);
      setActiveId(id);
      try {
        const up = await uploadFile(file, "video");
        patch(id, { url: up.url });
        await runSplit(id, up.url, method);
      } catch (e) {
        patch(id, { status: "error", error: e instanceof Error ? e.message : "上传失败" });
      }
    },
    [method, runSplit],
  );

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    files.forEach(addVideo);
    e.target.value = "";
  };

  /* ---------------- 选择拆分方式 ---------------- */
  if (view === "select") {
    return (
      <div className="mx-auto flex min-h-full max-w-5xl flex-col items-center justify-center px-8 py-16">
        <h1 className="font-display text-2xl font-bold text-ink">请选择拆分方式</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          批量上传视频，一键拆分切片，高效整理！
        </p>
        <div className="mt-10 grid w-full grid-cols-1 gap-6 sm:grid-cols-3">
          {METHODS.map((m) => {
            const Icon = m.icon;
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => {
                  setMethod(m.key);
                  setView("work");
                }}
                className="group relative aspect-[4/3] overflow-hidden rounded-2xl text-left shadow-lg transition hover:-translate-y-1 hover:shadow-xl"
                style={{ background: m.grad }}
              >
                <div className="absolute inset-0 bg-black/10" />
                <Icon className="absolute right-4 top-4 h-7 w-7 text-white/70" />
                <span className="absolute right-4 bottom-14 flex h-11 w-11 items-center justify-center rounded-full bg-white/25 backdrop-blur transition group-hover:scale-110">
                  <Play className="h-5 w-5 fill-white text-white" />
                </span>
                <div className="absolute inset-x-0 bottom-0 p-4">
                  <p className="text-base font-semibold text-white">{m.title}</p>
                  <p className="mt-0.5 text-xs text-white/75">{m.desc}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  /* ---------------- 工作区（同一路由，深色） ---------------- */
  return (
    <div className="flex h-full min-h-full flex-col bg-[#0f0f13] text-white">
      <input ref={fileRef} type="file" accept="video/*" multiple hidden onChange={onPick} />

      {/* 顶栏 */}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-white/10 px-5">
        <button
          type="button"
          onClick={() => setView("select")}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-white/80 transition hover:bg-white/10"
        >
          <ChevronLeft className="h-4 w-4" />
          AI分镜：{METHOD_LABEL[method]}
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* 左：视频列表 */}
        <aside className="flex w-72 shrink-0 flex-col border-r border-white/10">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="text-sm font-semibold">视频列表</span>
            <span className="text-xs text-white/45">共 {videos.length} 个视频</span>
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3">
            {videos.length === 0 ? (
              <p className="px-2 py-10 text-center text-xs text-white/40">
                还没有视频，点下方「添加视频」开始
              </p>
            ) : (
              videos.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setActiveId(v.id)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl border p-2 text-left transition",
                    v.id === activeId
                      ? "border-brand/60 bg-white/10"
                      : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]",
                  )}
                >
                  <div className="relative h-12 w-16 shrink-0 overflow-hidden rounded-md bg-black/40">
                    {v.clips[0]?.thumbnail ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={v.clips[0].thumbnail} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <Film className="absolute inset-0 m-auto h-5 w-5 text-white/30" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{v.name}</p>
                    <p className="mt-0.5 text-xs text-white/45">
                      {v.status === "uploading" && "上传中…"}
                      {v.status === "splitting" && "拆分中…"}
                      {v.status === "done" && `共 ${v.clips.length} 个切片`}
                      {v.status === "error" && "拆分失败"}
                    </p>
                  </div>
                </button>
              ))
            )}
          </div>
          <div className="flex gap-2 border-t border-white/10 p-3">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
              style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}
            >
              <Plus className="h-4 w-4" />
              添加视频
            </button>
            <button
              type="button"
              disabled={!active || active.status === "splitting" || !active.url}
              onClick={() => active && runSplit(active.id, active.url, method)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
              style={{ background: "linear-gradient(135deg,#db2777,#ef4444)" }}
            >
              <RotateCcw className="h-4 w-4" />
              重新拆分
            </button>
          </div>
        </aside>

        {/* 右：主区 */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          {!active ? (
            <Empty onAdd={() => fileRef.current?.click()} />
          ) : active.status === "uploading" || active.status === "splitting" ? (
            <Progress uploading={active.status === "uploading"} />
          ) : active.status === "error" ? (
            <ErrorView msg={active.error} onRetry={() => active.url && runSplit(active.id, active.url, method)} />
          ) : (
            <Clips video={active} />
          )}
        </main>
      </div>
    </div>
  );
}

function Empty({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center text-center">
      <button
        type="button"
        onClick={onAdd}
        className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-white/20 px-16 py-12 text-white/60 transition hover:border-brand/50 hover:text-white"
      >
        <Plus className="h-9 w-9" />
        <span className="text-sm">添加视频，开始 AI 拆分</span>
      </button>
    </div>
  );
}

function Progress({ uploading }: { uploading: boolean }) {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center">
      <h2 className="text-lg font-semibold">视频正在 AI 拆分，请耐心等待</h2>
      <div className="mt-7 w-72 space-y-3">
        <Step
          label={uploading ? "正在上传视频…" : "正在分析视频内容…"}
          tone="from-blue-500 to-indigo-600"
          done={!uploading}
          spinning={uploading}
        />
        <Step
          label="正在生成拆分点…"
          tone="from-fuchsia-600 to-rose-500"
          spinning={!uploading}
          dim={uploading}
        />
      </div>
      <div className="mt-7 h-1.5 w-72 overflow-hidden rounded-full bg-white/10">
        <div className="h-full w-2/3 animate-pulse rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500" />
      </div>
    </div>
  );
}

function Step({
  label,
  tone,
  done,
  spinning,
  dim,
}: {
  label: string;
  tone: string;
  done?: boolean;
  spinning?: boolean;
  dim?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-full bg-gradient-to-r px-4 py-2.5 text-sm",
        tone,
        dim && "opacity-40",
      )}
    >
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/25">
        {spinning ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : done ? (
          <Check className="h-3.5 w-3.5" />
        ) : null}
      </span>
      {label}
    </div>
  );
}

function ErrorView({ msg, onRetry }: { msg?: string; onRetry: () => void }) {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center text-center">
      <p className="text-sm text-rose-400">拆分失败：{msg ?? "未知错误"}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-lg border border-white/20 px-4 py-2 text-sm text-white/80 transition hover:bg-white/10"
      >
        重试
      </button>
    </div>
  );
}

function Clips({ video }: { video: Video }) {
  return (
    <div className="p-5">
      <div className="mb-4 flex items-center gap-2 text-sm text-white/70">
        <Scissors className="h-4 w-4 text-brand" />
        共 {video.clips.length} 个切片
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {video.clips.map((c) => (
          <div key={c.index} className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.03]">
            <div className="relative aspect-video bg-black/40">
              {c.thumbnail ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={c.thumbnail} alt="" className="h-full w-full object-cover" />
              ) : (
                <Film className="absolute inset-0 m-auto h-7 w-7 text-white/30" />
              )}
              <span className="absolute left-1.5 top-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[11px] font-medium">
                #{c.index}
              </span>
              <span className="absolute right-1.5 bottom-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[11px]">
                {c.duration.toFixed(1)}s
              </span>
            </div>
            <div className="flex items-center justify-between px-2.5 py-2 text-[11px] text-white/55">
              <span>{fmt(c.start)} → {fmt(c.end)}</span>
              {c.url && (
                <a href={c.url} target="_blank" rel="noreferrer" className="text-white/70 hover:text-brand" title="下载切片">
                  <Download className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
