// 素材生产 — shared types & config (mock-first; matches the eventual
// FastAPI ai-service contract so swapping to real generation is trivial).

export type MaterialTab =
  | "ai_studio" // AI影棚
  | "replica" // AI复刻
  | "element_swap" // 元素替换
  | "dubbing" // AI配音
  | "digital_human"; // 数字人

export const MATERIAL_TABS: { key: MaterialTab; label: string }[] = [
  { key: "ai_studio", label: "AI影棚" },
  { key: "replica", label: "AI复刻" },
  { key: "element_swap", label: "元素替换" },
  { key: "dubbing", label: "AI语音" },
  { key: "digital_human", label: "数字人" },
];

export type GenStatus = "processing" | "succeeded" | "failed";
export type ResultKind = "video" | "audio" | "image";

export interface GenSettings {
  model: string; // Seedance 2.0 …
  ratio: string; // 9:16 …
  resolution: string; // 720p …
  duration: number; // seconds
}

export interface GenJob {
  id: string;
  type: MaterialTab;
  status: GenStatus;
  kind?: ResultKind;
  progress?: number;
  thumbnailUrl?: string | null;
  resultUrl?: string | null;
  durationSec?: number;
  createdAt: string; // ISO
  title?: string;
}

// Deterministic ink-wash gradient for placeholder tiles — asset-independent,
// so the demo never shows broken images while real OSS thumbnails arrive later.
const TILE_PAIRS: [string, string][] = [
  ["#f3e0dc", "#e3a99d"],
  ["#ece2cd", "#d6bd8e"],
  ["#d8e8e1", "#a4cfc2"],
  ["#dde1f0", "#aebbe0"],
  ["#e7dff0", "#c7b0e0"],
  ["#efe6d6", "#d8c09f"],
];

export function tilePair(seed: string): [string, string] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return TILE_PAIRS[h % TILE_PAIRS.length];
}

export function tileGradient(seed: string): string {
  const [a, b] = tilePair(seed);
  return `linear-gradient(135deg, ${a}, ${b})`;
}

export const MODELS = ["Seedance 2.0", "Seedance 1.5", "Kling 1.6", "Vidu 2.0"];
export const RATIOS = ["9:16", "16:9", "1:1", "3:4", "4:3"];
export const RESOLUTIONS = ["480p", "720p", "1080p"];
export const DURATIONS = [5, 10];

export const COST_PER_SECOND = 3;
export const costOf = (s: GenSettings) =>
  s.duration * COST_PER_SECOND + (s.resolution === "1080p" ? 10 : 0);

export const DEFAULT_SETTINGS: GenSettings = {
  model: "Seedance 2.0",
  ratio: "9:16",
  resolution: "720p",
  duration: 5,
};

export type GeneratePayload = {
  settings?: GenSettings;
  durationSec?: number;
  sourceUrl?: string;
  refs?: string[];
  prompt?: string;
  voice?: string;
  ip?: string;
};

export type GenerateFn = (payload: GeneratePayload) => Promise<void>;

// ---- AI 语音 (Doubao TTS/ASR) ----
export type Voice = {
  id: string;
  name: string;
  scene: string;
  gender: string;
  langDialect: string;
  capabilities: string[];
  tags: string[];
  provider: string;
};

export type VoiceGeneratePayload = {
  text: string;
  speaker: string;
  voiceName?: string;
  emotion?: string;
};

export type VoiceGenerateFn = (p: VoiceGeneratePayload) => Promise<void>;

// AI 语音三种模式：文字转语音 / 语音翻译 / 语音克隆
export type VoiceMode = "tts" | "translate" | "clone";

export type Language = { code: string; name: string };

// 翻译：音频(或文本) -> ASR/翻译 -> 可选用所选音色合成译文音频
export type TranslatePayload = {
  audioUrl?: string;
  text?: string;
  source: string;
  target: string;
  speaker?: string;
  voiceName?: string;
};
export type TranslateResult = {
  ok: boolean;
  sourceText?: string;
  text?: string;
  url?: string | null;
};
export type TranslateFn = (p: TranslatePayload) => Promise<TranslateResult>;

// 语音克隆（VoxCPM）：参考音 + 文本 -> 克隆音频
export type ClonePayload = {
  text: string;
  referenceUrl: string;
  ultimate?: boolean;
  promptText?: string;
};
export type CloneFn = (p: ClonePayload) => Promise<void>;
