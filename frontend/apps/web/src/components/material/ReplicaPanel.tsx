"use client";

import { useState } from "react";
import {
  type GenerateFn,
  type GenSettings,
  DEFAULT_SETTINGS,
  costOf,
} from "./types";
import {
  Showcase,
  StickyBar,
  GenerateButton,
  SettingsChips,
  VideoDrop,
  ExamplesRow,
  useUpload,
} from "./shared";

export function ReplicaPanel({ onGenerate }: { onGenerate: GenerateFn }) {
  const up = useUpload("video");
  const [settings, setSettings] = useState<GenSettings>(DEFAULT_SETTINGS);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof GenSettings>(k: K, v: GenSettings[K]) =>
    setSettings((s) => ({ ...s, [k]: v }));

  async function gen() {
    setBusy(true);
    try {
      await onGenerate({
        settings,
        durationSec: settings.duration,
        sourceUrl: up.value?.url,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="上传视频，复刻生成新素材"
          subtitle="AI 解析爆款的脚本与运镜，一键产出同款新素材"
          examples={["/illus_cosmetics.webp", "/illus_people.webp", "/illus_gift.webp"]}
        />
        <div className="mt-5">
          <VideoDrop
            up={up}
            label="上传视频，复刻生成新素材"
            hint="支持 1080p 及以下的 mp4、mov，不超过 30MB，3–15s"
          />
        </div>
        <ExamplesRow
          title="应用示例"
          items={[
            { label: "空镜头", src: "/illus_river.webp" },
            { label: "3D动画", src: "/illus_mountain.webp" },
          ]}
        />
      </div>

      <StickyBar>
        <div className="flex flex-wrap items-center gap-2">
          <SettingsChips settings={settings} set={set} showModel={false} />
          <GenerateButton
            cost={costOf(settings) + 5}
            busy={busy}
            onClick={gen}
            className="ml-auto"
          />
        </div>
      </StickyBar>
    </div>
  );
}
