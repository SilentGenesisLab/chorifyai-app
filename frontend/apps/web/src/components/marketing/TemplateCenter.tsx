"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { TEMPLATES } from "@/lib/marketing";
import { SectionHeading } from "@/components/decor/ink";
import { SectionInk } from "./SectionInk";
import { TONE_COLOR, type Tone } from "./shared";
import { cn } from "@/lib/utils";

/** 模板卡 → 水墨场景插画（裁自资产2） */
const TEMPLATE_IMG = ["skincare", "giftbox", "zongzi", "landscape", "people"];

export function TemplateCenter() {
  const [active, setActive] = useState(0);

  return (
    <section id="templates" className="relative overflow-hidden py-20">
      <SectionInk posY="72%" />
      <div className="relative z-10 mx-auto max-w-7xl px-6">
        <SectionHeading title={TEMPLATES.title} />

        {/* tabs */}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-2">
          {TEMPLATES.tabs.map((t, i) => (
            <button
              key={t}
              type="button"
              onClick={() => setActive(i)}
              className={cn(
                "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                active === i
                  ? "brand-gradient text-white shadow-seal"
                  : "border border-border bg-surface text-muted-foreground hover:text-ink",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* cards */}
        <div className="mt-10 grid grid-cols-2 gap-5 md:grid-cols-3 lg:grid-cols-5">
          {TEMPLATES.cards.map((c, i) => {
            const color = TONE_COLOR[c.tone as Tone];
            return (
              <div
                key={c.title}
                className="group ink-card overflow-hidden p-0 transition hover:-translate-y-1 hover:shadow-lg"
              >
                <div className="relative aspect-[4/3] overflow-hidden bg-surface-muted">
                  <img
                    src={`/assets/ink/${TEMPLATE_IMG[i % TEMPLATE_IMG.length]}.webp`}
                    alt={c.title}
                    className="absolute inset-0 h-full w-full object-cover object-center transition-transform duration-300 group-hover:scale-105"
                  />
                  <span
                    className="absolute left-2.5 top-2.5 rounded-md px-2 py-0.5 text-[11px] font-medium text-white"
                    style={{ background: color }}
                  >
                    {c.badge}
                  </span>
                </div>
                <div className="p-3">
                  <h3 className="truncate text-sm font-semibold text-ink">{c.title}</h3>
                  <p className="mt-1 truncate text-xs text-muted-foreground">{c.desc}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-8 text-center">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand transition-colors hover:text-brand-deep"
          >
            查看全部模板
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
