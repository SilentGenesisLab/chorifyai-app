import { ArrowRight } from "lucide-react";
import { SOLUTIONS } from "@/lib/marketing";
import { SealBadge } from "@/components/decor/ink";
import { TONE_COLOR, type Tone } from "./shared";

/** 行业 → 水墨场景插画（裁自资产2） */
const SOLUTION_IMG = ["skincare", "giftbox", "people"];

export function IndustrySolutions() {
  return (
    <div id="solutions">
      <h2 className="flex items-center gap-2.5 font-display text-2xl font-bold text-ink">
        <SealBadge />
        {SOLUTIONS.title}
      </h2>

      <div className="mt-6 space-y-4">
        {SOLUTIONS.items.map((it, idx) => {
          const color = TONE_COLOR[it.tone as Tone];
          return (
            <div
              key={it.title}
              className="group ink-card flex items-center gap-4 p-4 transition hover:-translate-y-0.5 hover:shadow-lg"
            >
              {/* 水墨场景插画 */}
              <div className="relative h-20 w-28 shrink-0 overflow-hidden rounded-xl bg-surface-muted">
                <img
                  src={`/assets/ink/${SOLUTION_IMG[idx % SOLUTION_IMG.length]}.webp`}
                  alt={it.title}
                  className="absolute inset-0 h-full w-full object-cover"
                />
                <span
                  className="absolute left-2 top-2 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-white"
                  style={{ background: color }}
                >
                  {it.tag}
                </span>
              </div>

              <div className="min-w-0 flex-1">
                <h3 className="font-display text-lg font-bold text-ink">{it.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  {it.desc}
                </p>
              </div>
              <ArrowRight className="h-4 w-4 shrink-0 text-muted transition-colors group-hover:text-brand" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
