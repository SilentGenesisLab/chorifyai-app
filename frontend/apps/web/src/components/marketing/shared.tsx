import {
  FileText,
  Clapperboard,
  BarChart3,
  Brush,
  Globe,
  Compass,
  PenTool,
  Play,
  TrendingUp,
  FileSignature,
  Feather,
  FolderTree,
  Send,
  Users,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

/** string key (lib/marketing.ts) → lucide icon */
export const ICONS: Record<string, LucideIcon> = {
  fileText: FileText,
  clapper: Clapperboard,
  barChart: BarChart3,
  brush: Brush,
  globe: Globe,
  compass: Compass,
  penTool: PenTool,
  play: Play,
  trendingUp: TrendingUp,
  fileSignature: FileSignature,
  feather: Feather,
  folderTree: FolderTree,
  send: Send,
  users: Users,
};

export type Tone = "brand" | "jade" | "azure" | "gold" | "violet";

export const TONE_COLOR: Record<Tone, string> = {
  brand: "var(--color-brand)",
  jade: "var(--color-jade)",
  azure: "var(--color-azure)",
  gold: "var(--color-gold)",
  violet: "var(--color-violet)",
};

/** 彩色圆形图标徽（柔色底 + 实色描线图标），对应品牌系统的「功能模块图标」 */
export function IconChip({
  icon,
  tone = "brand",
  size = 52,
  className,
}: {
  icon: string;
  tone?: Tone;
  size?: number;
  className?: string;
}) {
  const Icon = ICONS[icon] ?? FileText;
  const color = TONE_COLOR[tone];
  return (
    <span
      className={cn("inline-flex items-center justify-center rounded-full", className)}
      style={{
        width: size,
        height: size,
        background: `color-mix(in srgb, ${color} 13%, #fff)`,
        color,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 22%, transparent)`,
      }}
    >
      <Icon style={{ width: size * 0.46, height: size * 0.46 }} strokeWidth={1.7} />
    </span>
  );
}
