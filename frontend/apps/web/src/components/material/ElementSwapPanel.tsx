"use client";

import { useState } from "react";
import { type GenerateFn, DEFAULT_SETTINGS, RESOLUTIONS } from "./types";
import { Dropdown } from "./Dropdown";
import {
  Showcase,
  StickyBar,
  GenerateButton,
  VideoDrop,
  ImageSlot,
  SectionLabel,
  useUpload,
} from "./shared";

export function ElementSwapPanel({ onGenerate }: { onGenerate: GenerateFn }) {
  const up = useUpload("video");
  const [refs, setRefs] = useState<(string | null)[]>([
    null,
    null,
    null,
    null,
    null,
  ]);
  const [prompt, setPrompt] = useState("");
  const [resolution, setResolution] = useState("720p");
  const [busy, setBusy] = useState(false);

  const setRef = (i: number) => (url: string | null) =>
    setRefs((r) => {
      const n = [...r];
      n[i] = url;
      return n;
    });

  async function gen() {
    setBusy(true);
    try {
      await onGenerate({
        settings: { ...DEFAULT_SETTINGS, resolution },
        durationSec: 5,
        sourceUrl: up.value?.url,
        refs: refs.filter(Boolean) as string[],
        prompt,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="替换视频里的产品 / 背景 / 文字"
          subtitle="一段视频，多种货品，批量产出带货素材"
          examples={["/illus_people.webp", "/illus_cosmetics.webp"]}
        />
        <div className="mt-5">
          <VideoDrop
            up={up}
            hint="支持 1080p 及以下的 mp4、mov，不超过 30MB，3–15s"
          />
        </div>

        <div className="mt-6">
          <SectionLabel hint="png/jpg/jpeg ≤ 10MB，宽/高 ≥ 400px">
            替换参考
          </SectionLabel>
          <div className="grid grid-cols-5 gap-2.5">
            {refs.map((_, i) => (
              <ImageSlot key={i} onChange={setRef(i)} label="上传参考" />
            ))}
          </div>
        </div>

        <div className="mt-6">
          <SectionLabel>需求描述</SectionLabel>
          <div className="relative">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value.slice(0, 2000))}
              rows={4}
              placeholder="将视频中的产品换成@图片1，背景换成@图片2，其他保持不变"
              className="w-full resize-none rounded-xl border border-border bg-surface px-3.5 py-3 text-sm outline-none placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <span className="absolute bottom-2.5 right-3 text-xs text-muted">
              {prompt.length} / 2000
            </span>
          </div>
        </div>
      </div>

      <StickyBar>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm">
            <span aria-hidden>🐴</span>
            <span className="font-medium">HappyHorse</span>
          </div>
          <Dropdown
            side="top"
            value={resolution}
            options={RESOLUTIONS.map((v) => ({ value: v }))}
            onChange={setResolution}
          />
          <GenerateButton
            busy={busy}
            disabled={!up.value}
            onClick={gen}
            className="ml-auto"
          />
        </div>
      </StickyBar>
    </div>
  );
}
