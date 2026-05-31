"use client";

import { useEffect, useRef, useState } from "react";
import {
  Mic,
  Loader2,
  ChevronRight,
  User,
  Upload,
  Music,
  X,
  Languages,
  AudioLines,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  type VoiceGenerateFn,
  type TranslateFn,
  type CloneFn,
  type Voice,
  type VoiceMode,
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
import { Dropdown } from "./Dropdown";
import { VoiceSelectModal } from "./VoiceSelectModal";
import { AiWritePopover } from "./AiWritePopover";
import { uploadFile } from "@/lib/upload";

const MODES: { key: VoiceMode; label: string }[] = [
  { key: "tts", label: "文字转语音" },
  { key: "translate", label: "语音翻译" },
  { key: "clone", label: "语音克隆" },
];

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

export function DubbingPanel({
  onVoiceGenerate,
  onTranslate,
  onClone,
}: {
  onVoiceGenerate: VoiceGenerateFn;
  onTranslate: TranslateFn;
  onClone: CloneFn;
}) {
  const [mode, setMode] = useState<VoiceMode>("tts");
  const [voice, setVoice] = useState<Voice | null>(null);
  const [emotion, setEmotion] = useState("默认");
  const [modalOpen, setModalOpen] = useState(false);
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

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-6">
        <Showcase
          title="AI 语音 · 100+ 音色 · 多语种"
          subtitle="文字转语音、外语音频翻译配音、参考音色克隆（豆包 / VoxCPM）"
        />

        {/* 模式切换 */}
        <div className="mt-5 flex rounded-xl border border-border bg-surface-muted/40 p-1">
          {MODES.map((m) => (
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

        <div className="mt-5">
          {mode === "tts" && (
            <TtsMode
              onVoiceGenerate={onVoiceGenerate}
              voice={voice}
              emotion={emotion}
              openVoice={() => setModalOpen(true)}
            />
          )}
          {mode === "translate" && (
            <TranslateMode
              onTranslate={onTranslate}
              langs={langs}
              voice={voice}
              emotion={emotion}
              openVoice={() => setModalOpen(true)}
            />
          )}
          {mode === "clone" && <CloneMode onClone={onClone} />}
        </div>
      </div>

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

/* ------------------------- 选择音色按钮 ------------------------- */
function VoicePickButton({
  voice,
  emotion,
  onClick,
  placeholder = "选择音色",
}: {
  voice: Voice | null;
  emotion: string;
  onClick: () => void;
  placeholder?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm transition hover:bg-surface-muted"
    >
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-soft text-brand">
        <User className="h-3 w-3" />
      </span>
      <span className="font-medium">{voice ? voice.name : placeholder}</span>
      {voice && emotion !== "默认" && (
        <span className="text-xs text-muted">· {emotion}</span>
      )}
      <ChevronRight className="h-3.5 w-3.5 text-muted" />
    </button>
  );
}

/* ------------------------- 音频上传 ------------------------- */
function AudioField({
  up,
  label,
  hint,
}: {
  up: UploadCtl;
  label: string;
  hint: string;
}) {
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
          className="flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border-strong bg-surface/60 py-6 transition hover:border-brand/50 hover:bg-brand-soft/30"
        >
          {up.uploading ? (
            <Loader2 className="h-6 w-6 animate-spin text-brand" />
          ) : (
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-muted">
              <Upload className="h-5 w-5" />
            </span>
          )}
          <span className="text-sm font-medium text-foreground">
            {up.uploading ? "上传中…" : label}
          </span>
          <span className="text-xs text-muted">{hint}</span>
        </button>
      )}
      {up.error && <p className="mt-2 text-xs text-brand">{up.error}</p>}
    </div>
  );
}

/* =======================  模式 1：文字转语音  ======================= */
function TtsMode({
  onVoiceGenerate,
  voice,
  emotion,
  openVoice,
}: {
  onVoiceGenerate: VoiceGenerateFn;
  voice: Voice | null;
  emotion: string;
  openVoice: () => void;
}) {
  const [text, setText] = useState("");
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
      if (d.ok && d.text) setText((t) => (t ? t + " " : "") + d.text);
      else alert(d.detail || "识别失败");
    } catch (e) {
      alert(e instanceof Error ? e.message : "识别失败");
    } finally {
      setAsrBusy(false);
    }
  }

  return (
    <>
      <div className="ink-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <span>请输入配音文本</span>
          <AiWritePopover onText={(t) => setText(t.slice(0, MAX))} maxChars={200} />
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
        <VoicePickButton voice={voice} emotion={emotion} onClick={openVoice} />
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
    </>
  );
}

/* =======================  模式 2：语音翻译  ======================= */
function TranslateMode({
  onTranslate,
  langs,
  voice,
  emotion,
  openVoice,
}: {
  onTranslate: TranslateFn;
  langs: Language[];
  voice: Voice | null;
  emotion: string;
  openVoice: () => void;
}) {
  const up = useUpload("audio");
  const [source, setSource] = useState("auto");
  const [target, setTarget] = useState("zh");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ sourceText?: string; text?: string } | null>(
    null,
  );

  const targetLangs = langs.filter((l) => l.code !== "auto");
  const nameOf = (code: string) =>
    langs.find((l) => l.code === code)?.name ?? code;

  async function run() {
    if (!up.value || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await onTranslate({
        audioUrl: up.value.url,
        source,
        target,
        speaker: voice?.id,
        voiceName: voice?.name,
      });
      if (r.ok) setResult({ sourceText: r.sourceText, text: r.text });
      else alert("翻译失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <SectionLabel hint="支持外语音频，自动识别 + 翻译">
        上传待翻译音频
      </SectionLabel>
      <AudioField up={up} label="上传音频" hint="mp3 / wav / m4a，单人清晰人声" />

      <div className="mt-4 flex items-center gap-2">
        <Dropdown
          label="原语种:"
          value={source}
          display={nameOf(source)}
          options={langs.map((l) => ({ value: l.code, label: l.name }))}
          onChange={setSource}
        />
        <Languages className="h-4 w-4 shrink-0 text-muted" />
        <Dropdown
          label="译为:"
          value={target}
          display={nameOf(target)}
          options={targetLangs.map((l) => ({ value: l.code, label: l.name }))}
          onChange={setTarget}
        />
      </div>

      <div className="mt-4">
        <SectionLabel hint="可选，选则用该音色朗读译文生成音频">
          译文配音音色
        </SectionLabel>
        <VoicePickButton
          voice={voice}
          emotion={emotion}
          onClick={openVoice}
          placeholder="不配音（仅出文本）"
        />
      </div>

      {result && (
        <div className="ink-card mt-4 space-y-3 p-4 text-sm">
          <div>
            <p className="mb-1 text-xs font-medium text-muted">识别原文</p>
            <p className="leading-relaxed text-muted-foreground">
              {result.sourceText || "—"}
            </p>
          </div>
          <div className="ink-rule" />
          <div>
            <p className="mb-1 text-xs font-medium text-brand">
              译文（{nameOf(target)}）
            </p>
            <p className="leading-relaxed text-foreground">{result.text || "—"}</p>
          </div>
        </div>
      )}

      <StickyBar>
        <GenerateButton
          busy={busy}
          disabled={!up.value}
          onClick={run}
          label={voice ? "翻译并配音" : "识别并翻译"}
          className="w-full"
        />
      </StickyBar>
    </>
  );
}

/* =======================  模式 3：语音克隆  ======================= */
function CloneMode({ onClone }: { onClone: CloneFn }) {
  const up = useUpload("audio");
  const [text, setText] = useState("");
  const [ultimate, setUltimate] = useState(false);
  const [promptText, setPromptText] = useState("");
  const [busy, setBusy] = useState(false);
  const [asrBusy, setAsrBusy] = useState(false);
  const [health, setHealth] = useState<{ ok: boolean; reason?: string } | null>(
    null,
  );
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
      <SectionLabel hint="≥3 秒、单人、清晰无背景音，效果更佳">
        上传参考音色
      </SectionLabel>
      <AudioField
        up={up}
        label="上传参考人声"
        hint="模型将复刻这段声音的音色"
      />

      <div className="mt-4 ink-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <AudioLines className="h-4 w-4 text-brand" />
          <span>克隆朗读文本</span>
          <AiWritePopover onText={(t) => setText(t.slice(0, MAX))} maxChars={200} />
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

      {/* 终极克隆（深度还原） */}
      <label className="mt-4 flex cursor-pointer items-start gap-2.5 rounded-xl border border-border bg-surface p-3">
        <input
          type="checkbox"
          checked={ultimate}
          onChange={(e) => setUltimate(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-[var(--color-brand)]"
        />
        <span className="text-sm">
          <span className="font-medium text-foreground">终极克隆（深度还原）</span>
          <span className="ml-1 text-xs text-muted">
            提供参考音的精确转写，相似度最高（~95%）
          </span>
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
          语音克隆服务未连接（VoxCPM）{health.reason ? ` · ${health.reason}` : ""}。
          请在后端配置 VOXCPM_URL 指向克隆服务。
        </p>
      )}

      <StickyBar>
        <GenerateButton
          busy={busy}
          disabled={disabled}
          onClick={gen}
          label="克隆生成"
          className="w-full"
        />
      </StickyBar>
    </>
  );
}
