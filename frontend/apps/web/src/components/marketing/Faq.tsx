"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { FAQ } from "@/lib/marketing";
import { SectionHeading } from "@/components/decor/ink";
import { cn } from "@/lib/utils";

export function Faq() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="mx-auto max-w-3xl px-6 py-20">
      <SectionHeading title={FAQ.title} />

      <div className="mt-12 space-y-3">
        {FAQ.items.map((item, i) => {
          const isOpen = open === i;
          return (
            <div key={item.q} className="ink-card overflow-hidden">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
              >
                <span className="font-medium text-ink">{item.q}</span>
                <Plus
                  className={cn(
                    "h-5 w-5 shrink-0 text-brand transition-transform duration-200",
                    isOpen && "rotate-45",
                  )}
                />
              </button>
              <div
                className={cn(
                  "grid transition-all duration-200",
                  isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                )}
              >
                <div className="overflow-hidden">
                  <p className="px-5 pb-4 text-sm leading-relaxed text-muted-foreground">
                    {item.a}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
