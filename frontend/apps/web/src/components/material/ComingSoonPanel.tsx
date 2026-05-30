import { SectionHeading } from "@/components/decor/ink";
import type { MaterialTab } from "./types";

const COPY: Record<Exclude<MaterialTab, "ai_studio">, { title: string; subtitle: string }> = {
  replica: { title: "AI复刻", subtitle: "上传一条爆款视频，AI 解析并复刻同款脚本与运镜" },
  element_swap: { title: "元素替换", subtitle: "替换视频中的产品、背景、文字，一图多用" },
  dubbing: { title: "AI配音", subtitle: "100+ 音色 · 多语言配音，文本一键转语音" },
  digital_human: { title: "数字人", subtitle: "真人级数字分身，口播带货不用真人出镜" },
};

export function ComingSoonPanel({ tab }: { tab: Exclude<MaterialTab, "ai_studio"> }) {
  const c = COPY[tab];
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 px-8 py-24 text-center">
      <SectionHeading title={c.title} subtitle={c.subtitle} />
      <span className="rounded-full border border-border bg-surface px-4 py-1.5 text-xs text-muted">
        该能力正在接入 · 敬请期待
      </span>
    </div>
  );
}
