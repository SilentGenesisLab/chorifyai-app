"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export function Dropdown({
  label,
  value,
  display,
  options,
  onChange,
  icon,
  side = "bottom",
  align = "start",
}: {
  label?: string;
  value: string;
  display?: string;
  options: { value: string; label?: string }[];
  onChange: (v: string) => void;
  icon?: React.ReactNode;
  side?: "top" | "bottom";
  align?: "start" | "end";
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
        className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-foreground transition hover:bg-surface-muted"
      >
        {icon}
        {label && <span className="text-muted-foreground">{label}</span>}
        <span className="font-medium">{display ?? value}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-muted transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-30 min-w-[130px] overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg",
            side === "top" ? "bottom-full mb-1.5" : "mt-1.5",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center justify-between gap-4 px-3 py-1.5 text-sm transition hover:bg-surface-muted",
                o.value === value ? "text-brand" : "text-foreground",
              )}
            >
              {o.label ?? o.value}
              {o.value === value && <Check className="h-3.5 w-3.5" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
