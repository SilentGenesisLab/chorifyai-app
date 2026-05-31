"use client";

import { useEffect, useRef, useState } from "react";
import {
  Mic,
  Loader2,
  ChevronRight,
  ChevronDown,
  User,
  Upload,
  Music,
  X,
  Languages,
  Trash2,
  Plus,
  Sparkles,
  Send,
  AudioLines,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  type VoiceGenerateFn,
  type TranslateFn,
  type CloneFn,
  type Voice,
  type Language,
} from "./types";
import {
  Showcase,
  StickyBar,
  GenerateButton,
  SectionLabel,
  useUpload,
  type UploadCtl,
} from "./shared";
import { VoiceSelectModal } from "./VoiceSelectModal";
import { uploadFile } from "@/lib/upload";

type PanelMode = "voice" | "clone";

type Segment = {
  id: string;
  text: string;
  voice: Voice | null;
  emotion: string;
};

const FALLBACK_LANGS: Language[] = [
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

let _sid = 0;
const newSeg = (): Segment => ({
  id: `seg_${Date.now().toString(36)}_${_sid++}`,
  text: "",
  voice: null,
  emotion: "默认",
});

export function DubbingPanel({
  onVoiceGenerate,
  onTranslate,
  onClone,
}: {
  onVoiceGenerate: VoiceGenerateFn;
  onTranslate: TranslateFn;
  onClone: CloneFn;
}) {
  const [mode, setMode] = useState<PanelMode>("voice");
  const [segments, setSegments] = useState<Segment[]>([newSeg()]);
  const [activeSeg, setActiveSeg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [langs, setLangs] = useState<Language[]>(FALLBACK_LANGS);

  useEffect(() => {
    fetch("/api/voice/languages")
      .then((r) => r.json())
      .then((d) => {
        if (d?.ok && Array.isArray(d.languages) && d.languages.length)
          setLangs(d.languages);
      })
      .catch(() => {});
  }, []);

  const patchSeg = (id: string, patch: Partial<Segment>) =>
    setSegments((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  const removeSeg = (id: string) =>
    setSegments((prev) => (prev.length > 1 ? prev.filter((s) => s.id !== id) : prev));
  const addSeg = () => setSegments((prev) => [...prev, newSeg()]);

  const activeModal = segments.find((s) => s.id === activeSeg) ?? null;
  const valid = segments.filter((s) => s.text.trim() && s.voice);
  const totalChars = segments.reduce((n, s) => n + s.text.trim().length, 0);

  async function genAll() {
    if (!valid.length || busy) return;
    setBusy(true);
    try {
      await Promise.all(
        valid.map((s) =>
          onVoiceGenerate({
            text: s.text.trim(),
            speaker: s.voice!.id,
            voiceName: s.voice!.name,
            emotion: s.emotion,
          }),
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="AI 语音 · 100+ 音色 · 多语种"
          subtitle="文字一键转语音；上传音频识别、一键翻译、AI 改写文案；或克隆参考音色"
        />

        {/* 模式切换 */}
        <div className="mt-5 flex rounded-xl border border-border bg-surface-muted/40 p-1">
          {(
            [
              { key: "voice", label: "配音" },
              { key: "clone", label: "声音克隆" },
            ] as { key: PanelMode; label: string }[]
          ).map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => setMode(m.key)}
              className={cn(
                "flex-1 rounded-lg py-2 text-sm font-medium transition",
                mode === m.key
                  ? "bg-surface text-brand shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        {mode === "voice" ? (
          <>
            <div className="mt-5 space-y-4">
              {segments.map((s, i) => (
                <SegmentCard
                  key={s.id}
                  index={i}
                  total={segments.length}
                  seg={s}
                  langs={langs}
                  onChange={(patch) => patchSeg(s.id, patch)}
                  onRemove={() => removeSeg(s.id)}
                  onPickVoice={() => setActiveSeg(s.id)}
                  onTranslate={onTranslate}
                />
              ))}
            </div>

            <button
              type="button"
              onClick={addSeg}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong py-2.5 text-sm text-muted transition hover:border-brand/50 hover:text-brand"
            >
              <Plus className="h-4 w-4" />
              添加配音段落
            </button>
          </>
        ) : (
          <div className="mt-5">
            <CloneMode onClone={onClone} />
          </div>
        )}
      </div>

      {mode === "voice" && (
        <StickyBar>
          <GenerateButton
            cost={totalChars}
            busy={busy}
            disabled={!valid.length}
            onClick={genAll}
            label={valid.length > 1 ? `生成 ${valid.length} 段配音` : "立即生成"}
            className="w-full"
          />
        </StickyBar>
      )}

      <VoiceSelectModal
        open={!!activeSeg}
        value={activeModal?.voice?.id}
        emotion={activeModal?.emotion ?? "默认"}
        onClose={() => setActiveSeg(null)}
        onConfirm={(v, e) => {
          if (activeSeg) patchSeg(activeSeg, { voice: v, emotion: e });
          setActiveSeg(null);
        }}
      />
    </div>
  );
}

/* =========================  单个配音段落  ========================= */
function SegmentCard({
  index,
  total,
  seg,
  langs,
  onChange,
  onRemove,
  onPickVoice,
  onTranslate,
}: {
  index: number;
  total: number;
  seg: Segment;
  langs: Language[];
  onChange: (patch: Partial<Segment>) => void;
  onRemove: () => void;
  onPickVoice: () => void;
  onTranslate: TranslateFn;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [asrBusy, setAsrBusy] = useState(false);
  const [trBusy, setTrBusy] = useState(false);
  const [chat, setChat] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const MAX = 500;

  // 上传音频 → ASR → 填入文本
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
      if (d.ok && d.text)
        onChange({ text: (seg.text ? seg.text + " " : "") + d.text });
      else alert(d.detail || "识别失败");
    } catch (e) {
      alert(e instanceof Error ? e.message : "识别失败");
    } finally {
      setAsrBusy(false);
    }
  }

  // 翻译当前文本 → 替换为译文
  async function translateTo(code: string) {
    if (!seg.text.trim() || trBusy) return;
    setTrBusy(true);
    try {
      const r = await onTranslate({ text: seg.text.trim(), source: "auto", target: code });
      if (r.ok && r.text) onChange({ text: r.text });
      else alert("翻译失败，请重试");
    } finally {
      setTrBusy(false);
    }
  }

  // 输入描述 → AI 改写上面的文本（base_text 为空则从零生成）
  async function runChat() {
    if (!chat.trim() || chatBusy) return;
    setChatBusy(true);
    try {
      const res = await fetch("/api/voice/write", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          prompt: chat.trim(),
          base_text: seg.text.trim() || undefined,
          max_chars: 300,
        }),
      });
      const d = await res.json();
      if (d.ok && d.text) {
        onChange({ text: d.text.slice(0, MAX) });
        setChat("");
      } else alert(d.detail || "生成失败");
    } catch (e) {
      alert(e instanceof Error ? e.message : "生成失败");
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <div className="ink-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">
          配音段落 {index + 1}
        </span>
        {total > 1 && (
          <button
            type="button"
            onClick={onRemove}
            className="text-muted transition hover:text-brand"
            aria-label="删除段落"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="relative">
        <textarea
          value={seg.text}
          onChange={(e) => onChange({ text: e.target.value.slice(0, MAX) })}
          rows={4}
          placeholder='输入要配音的文案，例如："你会做什么？"'
          className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted"
        />
        <span className="pointer-events-none absolute -bottom-1 right-0 text-xs text-muted">
          {seg.text.length}/{MAX}
        </span>
      </div>

      <div className="ink-rule my-3" />

      {/* 工具条：上传语音 / 翻译 / 音色 */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={(e) => onAudio(e.target.files?.[0])}
        />
        <ToolButton
          icon={asrBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mic className="h-3.5 w-3.5" />}
          onClick={() => fileRef.current?.click()}
          disabled={asrBusy}
        >
          {asrBusy ? "识别中…" : "上传语音"}
        </ToolButton>

        <TranslateMenu
          langs={langs}
          busy={trBusy}
          disabled={!seg.text.trim()}
          onPick={translateTo}
        />

        <button
          type="button"
          onClick={onPickVoice}
          className="ml-auto flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm transition hover:bg-surface-muted"
        >
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-soft text-brand">
            <User className="h-3 w-3" />
          </span>
          <span className="font-medium">{seg.voice ? seg.voice.name : "选择音色"}</span>
          {seg.voice && seg.emotion !== "默认" && (
            <span className="text-xs text-muted">· {seg.emotion}</span>
          )}
          <ChevronRight className="h-3.5 w-3.5 text-muted" />
        </button>
      </div>

      {/* AI 改写 chatbot：输入描述，对上面的文本进行更改 */}
      <div className="mt-3 flex items-center gap-2 rounded-xl border border-border bg-surface-muted/40 px-2.5 py-1.5">
        <Sparkles className="h-4 w-4 shrink-0 text-violet" />
        <input
          value={chat}
          onChange={(e) => setChat(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              runChat();
            }
          }}
          placeholder={seg.text.trim() ? "输入描述，让 AI 改写上面的文案…" : "让 AI 帮你写点什么…"}
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
        />
        <button
          type="button"
          onClick={runChat}
          disabled={chatBusy || !chat.trim()}
          className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-r from-violet to-azure text-white transition hover:opacity-90 disabled:opacity-40"
          aria-label="发送"
        >
          {chatBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
        </button>
      </div>
    </div>
  );
}

function ToolButton({
  icon,
  children,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-foreground transition hover:bg-surface-muted disabled:opacity-50"
    >
      {icon}
      {children}
    </button>
  );
}

function TranslateMenu({
  langs,
  busy,
  disabled,
  onPick,
}: {
  langs: Language[];
  busy: boolean;
  disabled: boolean;
  onPick: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled || busy}
        className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-foreground transition hover:bg-surface-muted disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Languages className="h-3.5 w-3.5" />
        )}
        {busy ? "翻译中…" : "翻译"}
        <ChevronDown className={cn("h-3.5 w-3.5 text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1.5 max-h-64 w-36 overflow-y-auto rounded-lg border border-border bg-surface py-1 shadow-lg">
          {langs
            .filter((l) => l.code !== "auto")
            .map((l) => (
              <button
                key={l.code}
                type="button"
                onClick={() => {
                  setOpen(false);
                  onPick(l.code);
                }}
                className="block w-full px-3 py-1.5 text-left text-sm text-foreground transition hover:bg-surface-muted"
              >
                译为{l.name}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

/* =========================  声音克隆（VoxCPM）  ========================= */
function CloneMode({ onClone }: { onClone: CloneFn }) {
  const up = useUpload("audio");
  const [text, setText] = useState("");
  const [ultimate, setUltimate] = useState(false);
  const [promptText, setPromptText] = useState("");
  const [busy, setBusy] = useState(false);
  const [asrBusy, setAsrBusy] = useState(false);
  const [health, setHealth] = useState<{ ok: boolean; reason?: string } | null>(null);
  const MAX = 500;

  useEffect(() => {
    fetch("/api/voice/clone/health")
      .then((r) => r.json())
      .then((d) => setHealth({ ok: !!d.ok, reason: d.reason }))
      .catch(() => setHealth({ ok: false, reason: "服务不可达" }));
  }, []);

  async function recognizeRef() {
    if (!up.value || asrBusy) return;
    setAsrBusy(true);
    try {
      const res = await fetch("/api/voice/asr", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: up.value.url }),
      });
      const d = await res.json();
      if (d.ok && d.text) setPromptText(d.text);
      else alert(d.detail || "识别失败");
    } catch (e) {
      alert(e instanceof Error ? e.message : "识别失败");
    } finally {
      setAsrBusy(false);
    }
  }

  async function gen() {
    if (!up.value || !text.trim() || busy) return;
    if (ultimate && !promptText.trim()) return;
    setBusy(true);
    try {
      await onClone({
        text: text.trim(),
        referenceUrl: up.value.url,
        ultimate,
        promptText: ultimate ? promptText.trim() : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  const disabled = !up.value || !text.trim() || (ultimate && !promptText.trim());

  return (
    <>
      <SectionLabel hint="≥3 秒、单人、清晰无背景音，效果更佳">上传参考音色</SectionLabel>
      <AudioField up={up} label="上传参考人声" hint="模型将复刻这段声音的音色" />

      <div className="mt-4 ink-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <AudioLines className="h-4 w-4 text-brand" />
          <span>克隆朗读文本</span>
        </div>
        <div className="relative">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX))}
            rows={4}
            placeholder="输入希望用克隆音色朗读的文案…"
            className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted"
          />
          <span className="pointer-events-none absolute -bottom-1 right-0 text-xs text-muted">
            {text.length}/{MAX}
          </span>
        </div>
      </div>

      <label className="mt-4 flex cursor-pointer items-start gap-2.5 rounded-xl border border-border bg-surface p-3">
        <input
          type="checkbox"
          checked={ultimate}
          onChange={(e) => setUltimate(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-[var(--color-brand)]"
        />
        <span className="text-sm">
          <span className="font-medium text-foreground">终极克隆（深度还原）</span>
          <span className="ml-1 text-xs text-muted">提供参考音的精确转写，相似度最高（~95%）</span>
        </span>
      </label>

      {ultimate && (
        <div className="mt-3 ink-card p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">
              参考音精确转写（须与参考音一字不差）
            </span>
            <button
              type="button"
              onClick={recognizeRef}
              disabled={!up.value || asrBusy}
              className="inline-flex items-center gap-1 text-xs text-brand transition hover:underline disabled:opacity-50"
            >
              {asrBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Mic className="h-3.5 w-3.5" />
              )}
              {asrBusy ? "识别中…" : "自动识别"}
            </button>
          </div>
          <textarea
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            rows={2}
            placeholder="参考音里说的原话…可点「自动识别」"
            className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted"
          />
        </div>
      )}

      {health && !health.ok && (
        <p className="mt-4 rounded-lg bg-brand-soft/50 px-3 py-2 text-xs text-brand">
          语音克隆服务未连接（VoxCPM）{health.reason ? ` · ${health.reason}` : ""}。请在后端配置 VOXCPM_URL 指向克隆服务。
        </p>
      )}

      <div className="mt-5">
        <GenerateButton busy={busy} disabled={disabled} onClick={gen} label="克隆生成" className="w-full" />
      </div>
    </>
  );
}

/* 音频上传卡片 */
function AudioField({ up, label, hint }: { up: UploadCtl; label: string; hint: string }) {
  return (
    <div>
      <input
        ref={up.inputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(e) => up.onFile(e.target.files?.[0])}
      />
      {up.value ? (
        <div className="ink-card flex items-center gap-3 p-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-muted text-brand">
            <Music className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">{up.value.name}</p>
            <p className="text-xs text-jade">已上传到云端</p>
          </div>
          <button type="button" onClick={up.clear} className="text-muted transition hover:text-brand">
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={up.pick}
          disabled={up.uploading}
          className="flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border-strong bg-surface/60 py-6 transition hover:border-brand/50 hover:bg-brand-soft/30"
        >
          {up.uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-brand" />
          ) : (
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-muted">
              <Upload className="h-5 w-5" />
            </span>
          )}
          <span className="text-sm font-medium text-foreground">{up.uploading ? "上传中…" : label}</span>
          <span className="text-xs text-muted">{hint}</span>
        </button>
      )}
      {up.error && <p className="mt-2 text-xs text-brand">{up.error}</p>}
    </div>
  );
}
