"use client";

import { useState } from "react";
import { Plus, User } from "lucide-react";
import { type GenerateFn } from "./types";
import { Dropdown } from "./Dropdown";
import { Showcase, StickyBar, GenerateButton } from "./shared";

const VOICES = [
  "TVB女星-港剧译制腔",
  "直率姐",
  "蜡笔小新",
  "阳光男孩",
  "知性女声",
  "沉稳男声",
];

export function DubbingPanel({ onGenerate }: { onGenerate: GenerateFn }) {
  const [text, setText] = useState("");
  const [voice, setVoice] = useState(VOICES[0]);
  const [busy, setBusy] = useState(false);
  const MAX = 400;

  async function gen() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await onGenerate({
        prompt: text,
        voice,
        durationSec: Math.max(2, Math.round(text.length / 4)),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="文本一键转语音 · 100+ 音色"
          subtitle="多语言配音，输入文案即可生成口播音频"
          examples={["/illus_people.webp"]}
        />

        <div className="ink-card mt-5 p-4">
          <div className="relative">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX))}
              rows={5}
              placeholder="输入要配音的文案，例如：你会做什么？"
              className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted"
            />
            <span className="pointer-events-none absolute right-0 top-0 text-xs text-muted">
              {text.length}/{MAX}
            </span>
          </div>
          <div className="ink-rule my-3" />
          <Dropdown
            icon={
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-soft text-brand">
                <User className="h-3 w-3" />
              </span>
            }
            value={voice}
            options={VOICES.map((v) => ({ value: v }))}
            onChange={setVoice}
          />
        </div>

        <button
          type="button"
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong py-2.5 text-sm text-muted transition hover:border-brand/50 hover:text-brand"
        >
          <Plus className="h-4 w-4" />
          添加配音段落
        </button>
      </div>

      <StickyBar>
        <GenerateButton
          cost={text.length}
          busy={busy}
          disabled={!text.trim()}
          onClick={gen}
          className="w-full"
        />
      </StickyBar>
    </div>
  );
}
