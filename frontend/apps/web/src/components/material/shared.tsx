"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import {
  Wand2,
  Loader2,
  Upload,
  X,
  ImagePlus,
  Film,
  Music,
  BarChart3,
  SlidersHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadFile, type UploadKind } from "@/lib/upload";
import { Dropdown } from "./Dropdown";
import {
  type GenSettings,
  MODELS,
  RATIOS,
  RESOLUTIONS,
  DURATIONS,
  tileGradient,
} from "./types";

/* ---------------- upload hook ---------------- */

export type Uploaded = { url: string; name: string } | null;

export function useUpload(
  kind: UploadKind,
  onChange?: (url: string | null) => void,
) {
  const [value, setValue] = useState<Uploaded>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onFile(f?: File | null) {
    if (!f) return;
    setError(null);
    setUploading(true);
    try {
      const r = await uploadFile(f, kind);
      setValue({ url: r.url, name: r.name });
      onChange?.(r.url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  function clear() {
    setValue(null);
    onChange?.(null);
  }

  return {
    value,
    uploading,
    error,
    inputRef,
    onFile,
    clear,
    pick: () => inputRef.current?.click(),
  };
}

export type UploadCtl = ReturnType<typeof useUpload>;

/* ---------------- layout bits ---------------- */

export function StickyBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="sticky bottom-0 border-t border-border bg-surface/90 px-5 py-3 backdrop-blur">
      {children}
    </div>
  );
}

export function GenerateButton({
  cost,
  busy,
  disabled,
  onClick,
  label = "立即生成",
  className,
}: {
  cost?: number;
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      className={cn(
        "brand-gradient inline-flex items-center justify-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-60",
        className,
      )}
    >
      {busy ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Wand2 className="h-4 w-4" />
      )}
      {busy ? "提交中…" : label}
      {typeof cost === "number" && (
        <span className="inline-flex items-center gap-0.5 rounded-full bg-white/20 px-1.5 py-0.5 text-xs">
          ✦ {cost}
        </span>
      )}
    </button>
  );
}

export function SettingsChips({
  settings,
  set,
  showModel = true,
}: {
  settings: GenSettings;
  set: <K extends keyof GenSettings>(k: K, v: GenSettings[K]) => void;
  showModel?: boolean;
}) {
  return (
    <>
      {showModel && (
        <Dropdown
          side="top"
          icon={<BarChart3 className="h-4 w-4 text-brand" />}
          value={settings.model}
          options={MODELS.map((v) => ({ value: v }))}
          onChange={(v) => set("model", v)}
        />
      )}
      <Dropdown
        side="top"
        icon={<SlidersHorizontal className="h-4 w-4 text-muted" />}
        value={settings.ratio}
        options={RATIOS.map((v) => ({ value: v }))}
        onChange={(v) => set("ratio", v)}
      />
      <Dropdown
        side="top"
        value={settings.resolution}
        options={RESOLUTIONS.map((v) => ({ value: v }))}
        onChange={(v) => set("resolution", v)}
      />
      <Dropdown
        side="top"
        value={`${settings.duration}s`}
        options={DURATIONS.map((d) => ({ value: `${d}s`, label: `${d} 秒` }))}
        onChange={(v) => set("duration", parseInt(v, 10))}
      />
    </>
  );
}

export function Showcase({
  title,
  subtitle,
  examples = [],
}: {
  title: string;
  subtitle: string;
  examples?: string[];
}) {
  return (
    <div className="ink-card relative overflow-hidden p-5">
      <div className="paper-grid pointer-events-none absolute inset-0 opacity-60" />
      <div className="relative flex items-center justify-between gap-5">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-bold text-ink">{title}</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
            {subtitle}
          </p>
        </div>
        {examples.length > 0 && (
          <div className="hidden shrink-0 items-center gap-2 lg:flex">
            {examples.slice(0, 3).map((src, i) => (
              <div
                key={i}
                className="h-20 w-16 rounded-lg border border-border"
                style={{ backgroundImage: tileGradient(src + i) }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function SectionLabel({
  children,
  hint,
}: {
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="mb-2.5 flex items-baseline gap-2">
      <span className="text-sm font-semibold text-foreground">{children}</span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}

/* ---------------- upload widgets ---------------- */

export function VideoDrop({
  up,
  hint,
  label = "上传视频",
  accept = "video/mp4,video/quicktime",
}: {
  up: UploadCtl;
  hint: string;
  label?: string;
  accept?: string;
}) {
  return (
    <div>
      <input
        ref={up.inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => up.onFile(e.target.files?.[0])}
      />
      {up.value ? (
        <div className="ink-card flex items-center gap-3 p-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-surface-muted text-brand">
            <Film className="h-6 w-6" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">
              {up.value.name}
            </p>
            <p className="text-xs text-jade">已上传到云端</p>
          </div>
          <button
            type="button"
            onClick={up.clear}
            className="text-muted transition hover:text-brand"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={up.pick}
          disabled={up.uploading}
          className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-strong bg-surface/60 text-center transition hover:border-brand/50 hover:bg-brand-soft/30"
        >
          {up.uploading ? (
            <Loader2 className="h-7 w-7 animate-spin text-brand" />
          ) : (
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-muted text-muted">
              <Upload className="h-6 w-6" />
            </span>
          )}
          <span className="text-[15px] font-medium text-foreground">
            {up.uploading ? "上传中…" : label}
          </span>
          <span className="text-xs text-muted-foreground">{hint}</span>
          <span className="text-xs text-muted">
            不能包含敏感内容（人脸/版权IP/不健康内容…）
          </span>
        </button>
      )}
      {up.error && <p className="mt-2 text-xs text-brand">{up.error}</p>}
    </div>
  );
}

export function ImageSlot({
  onChange,
  label = "上传参考",
  kind = "image",
  accept = "image/png,image/jpeg",
}: {
  onChange?: (url: string | null) => void;
  label?: string;
  kind?: UploadKind;
  accept?: string;
}) {
  const up = useUpload(kind, onChange);
  return (
    <div>
      <input
        ref={up.inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => up.onFile(e.target.files?.[0])}
      />
      {up.value ? (
        kind === "image" ? (
          <div className="relative aspect-square w-full overflow-hidden rounded-xl border border-border">
            <Image
              src={up.value.url}
              alt=""
              fill
              sizes="90px"
              className="object-cover"
              unoptimized
            />
            <button
              type="button"
              onClick={up.clear}
              className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/45 text-white"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div className="relative flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-xl border border-border bg-surface-muted text-jade">
            <Music className="h-5 w-5" />
            <span className="text-[11px]">已上传</span>
            <button
              type="button"
              onClick={up.clear}
              className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/45 text-white"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )
      ) : (
        <button
          type="button"
          onClick={up.pick}
          disabled={up.uploading}
          className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-border-strong text-muted transition hover:border-brand/50 hover:bg-brand-soft/30"
        >
          {up.uploading ? (
            <Loader2 className="h-5 w-5 animate-spin text-brand" />
          ) : (
            <ImagePlus className="h-5 w-5" />
          )}
          <span className="text-[11px]">{up.uploading ? "上传中" : label}</span>
        </button>
      )}
    </div>
  );
}

export function ExamplesRow({
  title,
  items,
}: {
  title: string;
  items: { label: string; src: string }[];
}) {
  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center justify-center gap-3">
        <span className="ink-rule w-12" />
        <span className="text-sm font-medium text-jade">{title}</span>
        <span className="ink-rule w-12" />
      </div>
      <div className="flex justify-center gap-3">
        {items.map((it, i) => (
          <div
            key={i}
            className="relative h-24 w-24 overflow-hidden rounded-xl border border-border shadow-sm"
            style={{ backgroundImage: tileGradient(it.label) }}
          >
            <span className="absolute inset-x-0 bottom-0 bg-black/40 py-0.5 text-center text-[11px] text-white backdrop-blur">
              {it.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
