"use client";

import { useRef, useState } from "react";
import { Plus, Mic, Loader2, ChevronRight, User } from "lucide-react";
import { type VoiceGenerateFn, type Voice } from "./types";
import { Showcase, StickyBar, GenerateButton } from "./shared";
import { VoiceSelectModal } from "./VoiceSelectModal";
import { uploadFile } from "@/lib/upload";

export function DubbingPanel({
  onVoiceGenerate,
}: {
  onVoiceGenerate: VoiceGenerateFn;
}) {
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<Voice | null>(null);
  const [emotion, setEmotion] = useState("默认");
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [asrBusy, setAsrBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const MAX = 500;

  async function gen() {
    if (!text.trim() || !voice) return;
    setBusy(true);
    try {
      await onVoiceGenerate({
        text: text.trim(),
        speaker: voice.id,
        voiceName: voice.name,
        emotion,
      });
    } finally {
      setBusy(false);
    }
  }

  async function onAudio(f?: File | null) {
    if (!f) return;
    setAsrBusy(true);
    try {
      const up = await uploadFile(f, "audio");
      const res = await fetch("/api/voice/asr", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: up.url }),
      });
      const d = await res.json();
      if (d.ok && d.text) {
        setText((t) => (t ? t + " " : "") + d.text);
      } else {
        alert(d.detail || d.error || "识别失败");
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "识别失败");
    } finally {
      setAsrBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="文本一键转语音 · 100+ 音色"
          subtitle="多语言 / 方言配音，输入文案或上传音频识别（豆包）"
        />

        <div className="ink-card mt-5 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
            <span>请输入您的配音文本</span>
            <span className="text-border-strong">/</span>
            <input
              ref={fileRef}
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={(e) => onAudio(e.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={asrBusy}
              className="inline-flex items-center gap-1 text-brand transition hover:underline"
            >
              {asrBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Mic className="h-3.5 w-3.5" />
              )}
              {asrBusy ? "识别中…" : "上传音频"}
            </button>
          </div>
          <div className="relative">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX))}
              rows={5}
              placeholder='例如"也许有些故事，没有结局，但我们依旧珍惜每个瞬间。"'
              className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted"
            />
            <span className="pointer-events-none absolute -bottom-1 right-0 text-xs text-muted">
              {text.length}/{MAX}
            </span>
          </div>
          <div className="ink-rule my-3" />
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm transition hover:bg-surface-muted"
          >
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-soft text-brand">
              <User className="h-3 w-3" />
            </span>
            <span className="font-medium">{voice ? voice.name : "选择音色"}</span>
            {voice && emotion !== "默认" && (
              <span className="text-xs text-muted">· {emotion}</span>
            )}
            <ChevronRight className="h-3.5 w-3.5 text-muted" />
          </button>
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
          disabled={!text.trim() || !voice}
          onClick={gen}
          className="w-full"
        />
      </StickyBar>

      <VoiceSelectModal
        open={modalOpen}
        value={voice?.id}
        emotion={emotion}
        onClose={() => setModalOpen(false)}
        onConfirm={(v, e) => {
          setVoice(v);
          setEmotion(e);
          setModalOpen(false);
        }}
      />
    </div>
  );
}
