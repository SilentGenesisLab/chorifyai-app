"use client";

import { Play, Loader2, Sparkles, Film } from "lucide-react";
import { cn, formatDateTime, formatDuration } from "@/lib/utils";
import { type GenJob, tileGradient } from "./types";

export function ResultsPanel({
  results,
  view,
}: {
  results: GenJob[];
  view: "grid" | "list";
}) {
  if (results.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-24 text-center text-muted">
        <Sparkles className="h-8 w-8 text-border-strong" />
        <p className="text-sm leading-relaxed">
          还没有生成记录
          <br />
          在左侧上传素材，点击「立即生成」试试
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "p-6",
        view === "grid"
          ? "grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] content-start gap-5"
          : "mx-auto max-w-3xl space-y-3",
      )}
    >
      {results.map((job) => (
        <ResultCard key={job.id} job={job} list={view === "list"} />
      ))}
    </div>
  );
}

function ResultCard({ job, list }: { job: GenJob; list: boolean }) {
  const isAudio = job.kind === "audio";
  return (
    <div className={cn(list && "ink-card flex items-center gap-4 p-3")}>
      <div className={cn(list ? "w-24 shrink-0" : "w-full")}>
        {isAudio ? <AudioFace job={job} /> : <VideoFace job={job} />}
      </div>
      <div className={cn(list ? "min-w-0 flex-1" : "")}>
        {list && (
          <p className="truncate text-sm font-medium text-foreground">
            {isAudio ? "AI 配音" : "AI 素材"}
          </p>
        )}
        <p className={cn("text-xs text-muted", !list && "mt-2")}>
          {formatDateTime(job.createdAt)}
        </p>
      </div>
    </div>
  );
}

function VideoFace({ job }: { job: GenJob }) {
  const processing = job.status === "processing";
  return (
    <Face seed={job.id}>
      {processing ? (
        <Processing progress={job.progress} />
      ) : (
        <>
          <span className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-white/25 text-white/85 backdrop-blur-sm">
            <Film className="h-6 w-6" />
          </span>
          <PlayBadge />
          {job.durationSec != null && <DurationBadge sec={job.durationSec} />}
        </>
      )}
      <AiBadge />
    </Face>
  );
}

function AudioFace({ job }: { job: GenJob }) {
  const processing = job.status === "processing";
  const bars = waveHeights(job.id);
  return (
    <Face seed={job.id} soft>
      <div
        className={cn(
          "relative flex h-1/2 w-full items-center justify-center gap-[3px] px-3",
          processing && "opacity-30",
        )}
      >
        {bars.map((b, i) => (
          <span
            key={i}
            className="w-[3px] shrink-0 rounded-full"
            style={{
              height: `${Math.round(b * 100)}%`,
              backgroundImage:
                "linear-gradient(to bottom, var(--color-azure), var(--color-violet))",
            }}
          />
        ))}
      </div>
      {processing ? (
        <Processing progress={job.progress} />
      ) : (
        <>
          <PlayBadge />
          {job.durationSec != null && <DurationBadge sec={job.durationSec} />}
        </>
      )}
      <AiBadge />
    </Face>
  );
}

function Face({
  children,
  seed,
  soft,
}: {
  children: React.ReactNode;
  seed: string;
  soft?: boolean;
}) {
  return (
    <div className="relative flex aspect-[3/4] w-full items-center justify-center overflow-hidden rounded-xl border border-border">
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: soft
            ? "linear-gradient(135deg, var(--color-surface-muted), #ece4d6)"
            : tileGradient(seed),
        }}
      />
      {children}
    </div>
  );
}

function Processing({ progress }: { progress?: number }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin text-brand" />
      <span className="text-xs font-medium">生成中 {progress ?? 0}%</span>
    </div>
  );
}

function PlayBadge() {
  return (
    <button
      type="button"
      className="absolute inset-0 flex items-center justify-center"
      aria-label="播放"
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur transition hover:bg-black/55">
        <Play className="h-5 w-5 translate-x-0.5" fill="currentColor" />
      </span>
    </button>
  );
}

function DurationBadge({ sec }: { sec: number }) {
  return (
    <span className="absolute bottom-2 right-2 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white">
      {formatDuration(sec)}
    </span>
  );
}

function AiBadge() {
  return (
    <span className="absolute left-2 top-2 rounded bg-black/35 px-1.5 py-0.5 text-[10px] text-white backdrop-blur">
      AI生成
    </span>
  );
}

function waveHeights(seed: string, n = 38): number[] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    h = (h * 1103515245 + 12345) & 0x7fffffff;
    const r = (h % 1000) / 1000;
    const edge = Math.sin((i / (n - 1)) * Math.PI);
    out.push(Math.max(0.12, (0.3 + r * 0.7) * (0.45 + 0.55 * edge)));
  }
  return out;
}
