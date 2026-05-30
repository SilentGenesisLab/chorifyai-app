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
  { key: "dubbing", label: "AI配音" },
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

// Mock video thumbnails reuse on-theme illustrations from /public.
const MOCK_THUMBS = [
  "/illus_people.webp",
  "/illus_cosmetics.webp",
  "/illus_river.webp",
  "/illus_gift.webp",
  "/illus_zongzi.webp",
  "/illus_mountain.webp",
];

export function mockThumb(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return MOCK_THUMBS[h % MOCK_THUMBS.length];
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
