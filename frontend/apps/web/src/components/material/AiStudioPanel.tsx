"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import {
  ImagePlus,
  X,
  BarChart3,
  SlidersHorizontal,
  MoreVertical,
  Sparkles,
  ArrowRight,
  Wand2,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadFile } from "@/lib/upload";
import { Dropdown } from "./Dropdown";
import {
  type GenSettings,
  type GenerateFn,
  DEFAULT_SETTINGS,
  MODELS,
  RATIOS,
  RESOLUTIONS,
  DURATIONS,
  costOf,
  tileGradient,
} from "./types";

const EXAMPLES = ["护肤精华", "吹风机", "口红", "咖啡杯"];

export function AiStudioPanel({ onGenerate }: { onGenerate: GenerateFn }) {
  const [image, setImage] = useState<{ url: string; name: string } | null>(null);
  const [settings, setSettings] = useState<GenSettings>(DEFAULT_SETTINGS);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [promo, setPromo] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const set = <K extends keyof GenSettings>(k: K, v: GenSettings[K]) =>
    setSettings((s) => ({ ...s, [k]: v }));

  async function onFile(f?: File | null) {
    if (!f) return;
    if (!f.type.startsWith("image/")) return;
    if (f.size > 10 * 1024 * 1024) {
      alert("图片需 ≤ 10MB");
      return;
    }
    setUploading(true);
    try {
      const r = await uploadFile(f, "image");
      setImage({ url: r.url, name: r.name });
    } catch (e) {
      alert(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleGenerate() {
    setBusy(true);
    try {
      await onGenerate({
        settings,
        durationSec: settings.duration,
        sourceUrl: image?.url,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        {/* 顶部展示横幅 */}
        <div className="ink-card relative overflow-hidden p-5">
          <div className="paper-grid pointer-events-none absolute inset-0 opacity-60" />
          <div className="relative flex items-center justify-between gap-6">
            <div className="min-w-0">
              <h2 className="font-display text-lg font-bold text-ink">
                上传产品图，一键生成商品大片
              </h2>
              <p className="mt-1.5 text-sm text-muted-foreground">
                AI 影棚自动出镜 · 自动运镜 · 自动卖点，10 秒出片
              </p>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="brand-gradient mt-3.5 inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium text-white shadow-seal transition hover:opacity-90"
              >
                <ImagePlus className="h-4 w-4" />
                上传产品图
              </button>
            </div>
            <div className="hidden shrink-0 items-center gap-2 sm:flex">
              <div
                className="h-20 w-16 rounded-lg border border-border"
                style={{ backgroundImage: tileGradient("studio-a") }}
              />
              <ArrowRight className="h-5 w-5 text-brand/70" />
              <div
                className="h-20 w-16 rounded-lg border border-border"
                style={{ backgroundImage: tileGradient("studio-b") }}
              />
              <div
                className="h-20 w-16 rounded-lg border border-border"
                style={{ backgroundImage: tileGradient("studio-c") }}
              />
            </div>
          </div>
        </div>

        {/* 上传区 */}
        <div className="mt-5">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/jpg"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          {image ? (
            <div className="relative mx-auto flex aspect-video max-w-xl items-center justify-center overflow-hidden rounded-2xl border border-border bg-surface-muted">
              <Image
                src={image.url}
                alt={image.name}
                fill
                sizes="640px"
                className="object-contain"
                unoptimized
              />
              <button
                type="button"
                onClick={() => setImage(null)}
                className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur transition hover:bg-black/60"
              >
                <X className="h-4 w-4" />
              </button>
              <span className="absolute bottom-3 left-3 max-w-[60%] truncate rounded bg-black/45 px-2 py-1 text-xs text-white">
                {image.name}
              </span>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border-strong bg-surface/60 text-center transition hover:border-brand/50 hover:bg-brand-soft/30 disabled:opacity-70"
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-muted text-muted">
                {uploading ? (
                  <Loader2 className="h-6 w-6 animate-spin text-brand" />
                ) : (
                  <ImagePlus className="h-6 w-6" />
                )}
              </span>
              <span className="text-[15px] font-medium text-foreground">
                {uploading ? "上传中…" : "上传产品/场景图"}
              </span>
              <span className="text-xs text-muted-foreground">
                jpg/jpeg/png ≤ 10MB，宽/高 ≥ 400px
              </span>
              <span className="text-xs text-muted">
                不能包含敏感内容（人脸/版权IP/不健康内容…）
              </span>
            </button>
          )}

        </div>

        {/* 影棚社区示例 */}
        <div className="mt-8">
          <p className="mb-3 text-center text-sm font-medium text-jade">
            没想好拍什么，去影棚社区看看 →
          </p>
          <div className="flex justify-center gap-3">
            {EXAMPLES.map((label, i) => (
              <div
                key={i}
                className={cn(
                  "relative h-24 w-20 overflow-hidden rounded-xl border border-border shadow-sm",
                  i % 2 === 0 ? "rotate-[-3deg]" : "rotate-[3deg]",
                )}
                style={{ backgroundImage: tileGradient(label) }}
              >
                <span className="absolute inset-x-0 bottom-0 bg-black/35 py-0.5 text-center text-[10px] text-white backdrop-blur">
                  {label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 底部生成工具条 */}
      <div className="sticky bottom-0 border-t border-border bg-surface/90 px-5 py-3 backdrop-blur">
        {promo && (
          <div className="mb-2.5 flex w-fit items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs text-brand-deep">
            <Sparkles className="h-3.5 w-3.5" />
            限时钜惠，低至 1 点/秒
            <button type="button" onClick={() => setPromo(false)} className="ml-1 text-brand/60 hover:text-brand">
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Dropdown
            side="top"
            icon={<BarChart3 className="h-4 w-4 text-brand" />}
            value={settings.model}
            options={MODELS.map((v) => ({ value: v }))}
            onChange={(v) => set("model", v)}
          />
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
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface text-muted transition hover:bg-surface-muted"
          >
            <MoreVertical className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={busy}
            className="brand-gradient ml-auto inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-60"
          >
            <Wand2 className="h-4 w-4" />
            {busy ? "提交中…" : "立即生成"}
            <span className="inline-flex items-center gap-0.5 rounded-full bg-white/20 px-1.5 py-0.5 text-xs">
              ✦ {costOf(settings)}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
