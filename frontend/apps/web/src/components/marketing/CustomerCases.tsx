import { Quote } from "lucide-react";
import { CASES } from "@/lib/marketing";
import { SealBadge } from "@/components/decor/ink";

const METRIC_TONES = ["var(--color-brand)", "var(--color-jade)", "var(--color-gold)"];

export function CustomerCases() {
  return (
    <div>
      <h2 className="flex items-center gap-2.5 font-display text-2xl font-bold text-ink">
        <SealBadge />
        {CASES.title}
      </h2>

      {/* 指标 */}
      <div className="mt-6 grid grid-cols-3 gap-4">
        {CASES.metrics.map((m, i) => (
          <div key={m.label} className="ink-card px-3 py-5 text-center">
            <div
              className="font-display text-3xl font-bold"
              style={{ color: METRIC_TONES[i % METRIC_TONES.length] }}
            >
              {m.value}
            </div>
            <div className="mt-1.5 text-xs text-muted-foreground">{m.label}</div>
          </div>
        ))}
      </div>

      {/* 合作品牌 */}
      <p className="mt-7 text-sm font-medium text-muted-foreground">合作品牌</p>
      <div className="mt-3 grid grid-cols-4 gap-2.5">
        {CASES.brands.map((b) => (
          <div
            key={b}
            className="flex h-12 items-center justify-center rounded-lg border border-border bg-surface px-2 text-center text-xs font-medium text-muted-foreground"
          >
            {b}
          </div>
        ))}
      </div>

      {/* 证言 */}
      <div className="ink-card mt-6 p-5">
        <Quote className="h-6 w-6 text-brand/30" />
        <p className="mt-2 text-sm leading-relaxed text-ink">{CASES.testimonial.quote}</p>
        <div className="mt-4 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft text-sm font-bold text-brand">
            完
          </span>
          <span className="text-sm text-muted-foreground">{CASES.testimonial.author}</span>
        </div>
      </div>
    </div>
  );
}
