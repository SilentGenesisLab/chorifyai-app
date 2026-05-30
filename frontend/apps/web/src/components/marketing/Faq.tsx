"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { FAQ } from "@/lib/marketing";
import { SectionHeading } from "@/components/decor/ink";
import { SectionInk } from "./SectionInk";
import { cn } from "@/lib/utils";

export function Faq() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="relative overflow-hidden py-20">
      <SectionInk posY="78%" />
      <div className="relative z-10 mx-auto max-w-6xl px-6">
        <SectionHeading title={FAQ.title} />

        {/* 水平排列的问题胶囊 */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-3">
          {FAQ.items.map((item, i) => {
            const isOpen = open === i;
            return (
              <button
                key={item.q}
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                className={cn(
                  "flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-medium transition-colors",
                  isOpen
                    ? "border-brand/40 bg-brand-soft text-brand"
                    : "border-border bg-surface/80 text-ink hover:border-brand/30 hover:text-brand",
                )}
              >
                {item.q}
                <Plus
                  className={cn(
                    "h-4 w-4 shrink-0 transition-transform duration-200",
                    isOpen ? "rotate-45 text-brand" : "text-muted",
                  )}
                />
              </button>
            );
          })}
        </div>

        {/* 选中问题的答案 */}
        {open !== null && (
          <div className="mx-auto mt-6 max-w-3xl">
            <div className="ink-card p-6 text-center">
              <p className="text-[15px] leading-relaxed text-muted-foreground">
                {FAQ.items[open].a}
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
