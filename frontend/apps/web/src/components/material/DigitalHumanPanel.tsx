"use client";

import { useState } from "react";
import Image from "next/image";
import { UserSquare } from "lucide-react";
import { cn } from "@/lib/utils";
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
  ImageSlot,
  SectionLabel,
} from "./shared";

const IPS = [
  { id: "ip_lijie", name: "李姐", src: "/illus_people.webp" },
  { id: "ip_expert", name: "专家", src: "/illus_cosmetics.webp" },
  { id: "ip_xiaohe", name: "小何", src: "/illus_gift.webp" },
  { id: "ip_lab", name: "实验员", src: "/illus_river.webp" },
];

export function DigitalHumanPanel({ onGenerate }: { onGenerate: GenerateFn }) {
  const [ip, setIp] = useState<string | null>(null);
  const [ipOpen, setIpOpen] = useState(false);
  const [bg, setBg] = useState<string | null>(null);
  const [item, setItem] = useState<string | null>(null);
  const [voice, setVoice] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [settings, setSettings] = useState<GenSettings>(DEFAULT_SETTINGS);
  const [busy, setBusy] = useState(false);
  const MAX = 120;

  const set = <K extends keyof GenSettings>(k: K, v: GenSettings[K]) =>
    setSettings((s) => ({ ...s, [k]: v }));
  const selected = IPS.find((x) => x.id === ip);

  async function gen() {
    setBusy(true);
    try {
      await onGenerate({
        settings,
        durationSec: settings.duration,
        ip: ip ?? undefined,
        refs: [bg, item, voice].filter(Boolean) as string[],
        prompt: text,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="真人级数字分身，口播带货"
          subtitle="选择数字人 IP，输入台词，自动出镜口播"
          examples={["/illus_people.webp"]}
        />

        <div className="mt-5">
          {selected ? (
            <div className="ink-card flex items-center gap-3 p-3">
              <div className="relative h-14 w-14 overflow-hidden rounded-lg">
                <Image src={selected.src} alt="" fill sizes="56px" className="object-cover" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-foreground">{selected.name}</p>
                <p className="text-xs text-muted">数字人 IP</p>
              </div>
              <button
                type="button"
                onClick={() => setIpOpen((o) => !o)}
                className="text-xs text-brand hover:underline"
              >
                更换
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIpOpen((o) => !o)}
              className="flex aspect-[16/7] w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border-strong text-muted transition hover:border-brand/50 hover:bg-brand-soft/30"
            >
              <UserSquare className="h-7 w-7" />
              <span className="text-sm font-medium text-foreground">选择数字人 IP</span>
            </button>
          )}
          {ipOpen && (
            <div className="mt-3 grid grid-cols-4 gap-2.5 rounded-xl border border-border bg-surface p-3">
              {IPS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setIp(p.id);
                    setIpOpen(false);
                  }}
                  className={cn(
                    "relative overflow-hidden rounded-lg border-2",
                    ip === p.id ? "border-brand" : "border-transparent",
                  )}
                >
                  <div className="relative aspect-[3/4]">
                    <Image src={p.src} alt={p.name} fill sizes="80px" className="object-cover" />
                  </div>
                  <span className="absolute inset-x-0 bottom-0 bg-black/45 py-0.5 text-center text-[11px] text-white">
                    {p.name}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="mt-6">
          <SectionLabel hint="png/jpg/jpeg ≤ 10MB，300–6000px · mp3/wav 2–15s">
            参考元素
          </SectionLabel>
          <div className="grid grid-cols-3 gap-2.5">
            <ImageSlot onChange={setBg} label="上传背景" />
            <ImageSlot onChange={setItem} label="上传物品" />
            <ImageSlot
              onChange={setVoice}
              label="上传音色"
              kind="audio"
              accept="audio/mpeg,audio/wav"
            />
          </div>
        </div>

        <div className="mt-6">
          <SectionLabel>口播台词</SectionLabel>
          <div className="relative">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX))}
              rows={3}
              placeholder="输入需要数字人说的语种和台词，例如：（粤语）三点几啦，饮茶啦老友"
              className="w-full resize-none rounded-xl border border-border bg-surface px-3.5 py-3 text-sm outline-none placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <span className="absolute bottom-2.5 right-3 text-xs text-muted">
              {text.length}/{MAX}
            </span>
          </div>
        </div>
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
