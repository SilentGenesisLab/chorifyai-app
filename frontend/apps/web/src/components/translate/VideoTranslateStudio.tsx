"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  UploadCloud,
  Loader2,
  Eraser,
  Captions,
  AudioLines,
  HelpCircle,
  Languages,
  Play,
  Download,
  RotateCcw,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import { uploadFile } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Lang = { code: string; name: string };
type Status = "uploading" | "processing" | "done" | "error";
type Task = {
  id: string;
  name: string;
  videoUrl: string; // 原视频（处理中作占位预览）
  sourceLabel: string;
  targetLabel: string;
  status: Status;
  stage?: string;
  progress?: { done: number; total: number };
  resultUrl?: string;
  error?: string;
  createdAt: string;
};

// 兜底语言表（后端 /api/voice/languages 拉取失败时用）
const LANG_FALLBACK: Lang[] = [
  { code: "auto", name: "自动识别" },
  { code: "zh", name: "中文" },
  { code: "en", name: "英语" },
  { code: "ja", name: "日语" },
  { code: "ko", name: "韩语" },
  { code: "th", name: "泰语" },
  { code: "vi", name: "越南语" },
  { code: "id", name: "印尼语" },
  { code: "es", name: "西班牙语" },
  { code: "fr", name: "法语" },
  { code: "de", name: "德语" },
  { code: "ru", name: "俄语" },
  { code: "pt", name: "葡萄牙语" },
  { code: "ar", name: "阿拉伯语" },
];

const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);
const nowLabel = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

export function VideoTranslateStudio() {
  const [langs, setLangs] = useState<Lang[]>(LANG_FALLBACK);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [source, setSource] = useState("auto");
  const [target, setTarget] = useState("");
  const [genSub, setGenSub] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/voice/languages")
      .then((r) => r.json())
      .then((d) => Array.isArray(d?.languages) && d.languages.length && setLangs(d.languages))
      .catch(() => {});
  }, []);

  // 释放本地预览 URL
  useEffect(() => () => void (previewUrl && URL.revokeObjectURL(previewUrl)), [previewUrl]);

  const langName = (code: string) => langs.find((l) => l.code === code)?.name ?? code;
  const targetLangs = langs.filter((l) => l.code !== "auto");

  const pickFile = (f: File | undefined) => {
    if (!f) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
  };

  const patch = (id: string, p: Partial<Task>) =>
    setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, ...p } : t)));

  const safeJson = async (r: Response) => {
    try {
      return await r.json();
    } catch {
      return null;
    }
  };

  const generate = useCallback(async () => {
    if (!file || !target || busy) return;
    setBusy(true);
    const id = uid();
    const task: Task = {
      id,
      name: file.name,
      videoUrl: previewUrl,
      sourceLabel: langName(source),
      targetLabel: langName(target),
      status: "uploading",
      stage: "上传视频",
      createdAt: nowLabel(),
      progress: { done: 0, total: 0 },
    };
    setTasks((ts) => [task, ...ts]);
    try {
      const up = await uploadFile(file, "video");
      patch(id, { videoUrl: up.url, status: "processing", stage: "排队中" });

      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: up.url,
          source,
          target,
          keep_bgm: true,
          generate_subtitles: genSub,
        }),
      });
      const start = await safeJson(res);
      if (!res.ok || !start?.job_id) {
        throw new Error(start?.detail || start?.error || `启动失败（HTTP ${res.status}）`);
      }
      const jobId: string = start.job_id;
      // 轮询（深度克隆较慢，最多 ~15 min）
      for (let i = 0; i < 450; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const pr = await fetch(`/api/translate/${jobId}`);
        const pj = await safeJson(pr);
        if (!pr.ok) throw new Error(pj?.detail || pj?.error || `查询失败（HTTP ${pr.status}）`);
        if (pj?.status === "done") {
          patch(id, { status: "done", stage: "完成", resultUrl: pj.url });
          return;
        }
        if (pj?.status === "failed") throw new Error(pj.error || "翻译失败");
        patch(id, { stage: pj?.stage, progress: pj?.progress });
      }
      throw new Error("处理超时，请重试");
    } catch (e) {
      patch(id, { status: "error", error: e instanceof Error ? e.message : "翻译失败" });
    } finally {
      setBusy(false);
    }
  }, [file, target, source, genSub, busy, previewUrl, langs]);

  const canGenerate = !!file && !!target && !busy;

  return (
    <div className="flex h-full min-h-full flex-col gap-6 overflow-y-auto p-6 lg:flex-row">
      {/* ───── 左：表单 ───── */}
      <section className="ink-card flex w-full shrink-0 flex-col p-6 lg:w-[440px]">
        <div className="text-center">
          <h1 className="font-display text-2xl font-bold text-ink">视频翻译</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            一键转换视频语言，助力全球视频生意
          </p>
        </div>

        {/* 上传区 */}
        <input
          ref={fileRef}
          type="file"
          accept="video/mp4,video/quicktime,video/*"
          hidden
          onChange={(e) => {
            pickFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="group mt-6 flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border-strong bg-surface/60 px-6 py-9 text-center transition-colors hover:border-brand/50 hover:bg-surface-muted"
        >
          {previewUrl ? (
            <>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video src={previewUrl} className="h-28 rounded-lg object-cover" muted />
              <span className="max-w-full truncate text-sm font-medium text-ink">{file?.name}</span>
              <span className="text-xs text-muted">点击重新选择</span>
            </>
          ) : (
            <>
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand text-white shadow-seal transition group-hover:scale-105">
                <UploadCloud className="h-6 w-6" />
              </span>
              <span className="text-sm font-medium text-ink">上传视频</span>
              <span className="text-xs text-muted">
                支持文件格式 mp4、mov，文件最大支持 1GB，最大时长 6min
              </span>
            </>
          )}
        </button>

        {/* 语言 */}
        <Field label="源语言" required>
          <LangSelect value={source} onChange={setSource} options={langs} placeholder="请选择" />
        </Field>
        <Field label="目标语言" required>
          <LangSelect value={target} onChange={setTarget} options={targetLangs} placeholder="请选择" />
        </Field>

        {/* 选项 */}
        <div className="mt-5 space-y-2.5">
          <ToggleRow icon={Eraser} label="擦除原字幕" disabled hint="即将支持" />
          <ToggleRow
            icon={Captions}
            label="生成新字幕"
            checked={genSub}
            onChange={setGenSub}
            hint="将译文烧录为字幕"
          />
          <ToggleRow icon={AudioLines} label="对口型" disabled hint="即将支持" />
        </div>

        <button
          type="button"
          disabled={!canGenerate}
          onClick={generate}
          className="brand-gradient mt-6 flex h-12 w-full items-center justify-center gap-2 rounded-xl text-base font-medium text-white shadow-seal transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Sparkles className="h-5 w-5" />}
          {busy ? "处理中…" : "立即生成"}
        </button>
      </section>

      {/* ───── 右：任务列表 ───── */}
      <section className="min-w-0 flex-1">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <h2 className="font-display text-lg font-bold text-ink">任务列表</h2>
            <span className="text-xs text-muted">内容由 AI 生成</span>
          </div>
        </div>

        {tasks.length === 0 ? (
          <div className="flex min-h-[50vh] flex-col items-center justify-center rounded-2xl border border-dashed border-border text-center">
            <Languages className="h-10 w-10 text-muted" />
            <p className="mt-3 text-sm text-muted-foreground">
              上传视频并选择语言，点击「立即生成」开始翻译
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {tasks.map((t) => (
              <TaskRow key={t.id} task={t} onRetry={generate} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

/* ---------------- 子组件 ---------------- */
function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-5">
      <label className="mb-1.5 block text-sm font-medium text-ink">
        {label}
        {required && <span className="ml-0.5 text-brand">*</span>}
      </label>
      {children}
    </div>
  );
}

function LangSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Lang[];
  placeholder: string;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "h-11 w-full appearance-none rounded-xl border border-border bg-surface px-3.5 pr-9 text-sm transition-colors focus:border-brand focus:outline-none",
          value ? "text-ink" : "text-muted",
        )}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((l) => (
          <option key={l.code} value={l.code} className="text-ink">
            {l.name}
          </option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  );
}

function ToggleRow({
  icon: Icon,
  label,
  checked,
  onChange,
  disabled,
  hint,
}: {
  icon: typeof Eraser;
  label: string;
  checked?: boolean;
  onChange?: (v: boolean) => void;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-xl border border-border bg-surface px-3.5 py-3",
        disabled && "opacity-60",
      )}
    >
      <Icon className="h-[18px] w-[18px] text-muted" />
      <span className="text-sm text-ink">{label}</span>
      {hint && (
        <span className="flex items-center gap-1 text-xs text-muted" title={hint}>
          <HelpCircle className="h-3.5 w-3.5" />
          {disabled && hint}
        </span>
      )}
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        aria-pressed={!!checked}
        className={cn(
          "relative ml-auto h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed",
          checked ? "bg-brand" : "bg-border-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-[22px]" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}

function TaskRow({ task, onRetry }: { task: Task; onRetry: () => void }) {
  const processing = task.status === "uploading" || task.status === "processing";
  const prog =
    task.progress && task.progress.total > 1
      ? `${task.progress.done}/${task.progress.total}`
      : "";
  return (
    <div>
      <div className="mb-2 flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand/10 text-brand">
          <Languages className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{task.createdAt}</p>
          <p className="truncate text-xs text-muted">
            {task.name} ｜ 源语言：{task.sourceLabel}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 pl-12 sm:grid-cols-2 xl:grid-cols-3">
        <div className="relative overflow-hidden rounded-xl border border-border bg-black/80">
          <span className="absolute right-2 top-2 z-10 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white">
            {task.targetLabel}
          </span>
          <div className="relative aspect-[9/16] max-h-72 w-full">
            {task.status === "done" && task.resultUrl ? (
              // eslint-disable-next-line jsx-a11y/media-has-caption
              <video src={task.resultUrl} controls className="h-full w-full bg-black object-contain" />
            ) : task.status === "error" ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
                <AlertCircle className="h-7 w-7 text-rose-400" />
                <p className="text-xs text-rose-300">{task.error ?? "翻译失败"}</p>
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-1 flex items-center gap-1 rounded-lg border border-white/20 px-3 py-1.5 text-xs text-white/85 transition hover:bg-white/10"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  重试
                </button>
              </div>
            ) : (
              <>
                {task.videoUrl && (
                  // eslint-disable-next-line jsx-a11y/media-has-caption
                  <video
                    src={task.videoUrl}
                    className="h-full w-full object-contain opacity-40"
                    muted
                    preload="metadata"
                  />
                )}
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center">
                  <Loader2 className="h-7 w-7 animate-spin text-white/90" />
                  <p className="text-sm font-medium text-white">正在翻译</p>
                  <p className="text-xs text-white/70">
                    {task.stage ?? "处理中"}
                    {prog && ` ${prog}`}
                  </p>
                </div>
              </>
            )}
          </div>
          {task.status === "done" && task.resultUrl && (
            <div className="flex items-center justify-between px-3 py-2">
              <span className="flex items-center gap-1 text-xs text-emerald-600">
                <Play className="h-3.5 w-3.5" />
                翻译完成
              </span>
              <a
                href={task.resultUrl}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-brand"
                title="下载译制视频"
              >
                <Download className="h-3.5 w-3.5" />
                下载
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
