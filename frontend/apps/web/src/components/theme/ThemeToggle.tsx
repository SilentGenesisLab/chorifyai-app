"use client";

import { useEffect, useState } from "react";
import { Sun, Moon, Monitor, Check } from "lucide-react";
import { cn } from "@/lib/utils";

type Theme = "light" | "dark" | "system";

const OPTIONS = [
  { key: "light" as const, label: "浅色", Icon: Sun },
  { key: "dark" as const, label: "深色", Icon: Moon },
  { key: "system" as const, label: "跟随系统", Icon: Monitor },
];

function applyTheme(t: Theme) {
  const dark =
    t === "dark" ||
    (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** 主题切换：浅色 / 深色 / 跟随系统（默认）。状态存 localStorage，跟随系统时实时响应 OS 变化。 */
export function ThemeToggle({ up = false, className }: { up?: boolean; className?: string }) {
  const [theme, setTheme] = useState<Theme>("system");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setTheme((localStorage.getItem("theme") as Theme | null) ?? "system");
  }, []);

  // 跟随系统时，OS 切换深浅色实时生效
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const choose = (t: Theme) => {
    localStorage.setItem("theme", t);
    setTheme(t);
    applyTheme(t);
    setOpen(false);
  };

  const Active = (OPTIONS.find((o) => o.key === theme) ?? OPTIONS[2]).Icon;

  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="切换主题"
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:border-brand/30 hover:text-brand"
      >
        <Active className="h-[18px] w-[18px]" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden />
          <div
            className={cn(
              "ink-card absolute right-0 z-50 w-36 p-1.5",
              up ? "bottom-full mb-2" : "top-full mt-2",
            )}
          >
            {OPTIONS.map(({ key, label, Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => choose(key)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-surface-muted hover:text-ink"
              >
                <Icon className="h-4 w-4" />
                {label}
                {theme === key && <Check className="ml-auto h-4 w-4 text-brand" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
