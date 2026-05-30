"use client";

import { useState } from "react";
import {
  FileText,
  Clapperboard,
  Copy,
  Shuffle,
  Mic,
  User,
  Wand2,
  Languages,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Tool = {
  label: string;
  icon: LucideIcon;
  badge?: string;
  grad: [string, string];
};

const TOOLS: Tool[] = [
  { label: "编写脚本", icon: FileText, grad: ["#7c5cff", "#a78bfa"] },
  { label: "AI影棚", icon: Clapperboard, badge: "New", grad: ["#ff5b8a", "#ff8fab"] },
  { label: "AI复刻", icon: Copy, grad: ["#22c1c3", "#4dd0e1"] },
  { label: "元素替换", icon: Shuffle, grad: ["#f7971e", "#ffd200"] },
  { label: "多语言AI配音", icon: Mic, grad: ["#6a11cb", "#2575fc"] },
  { label: "数字人视频", icon: User, grad: ["#00b09b", "#96c93d"] },
  { label: "超级混剪Pro", icon: Wand2, badge: "New", grad: ["#fc466b", "#3f5efb"] },
  { label: "视频翻译", icon: Languages, grad: ["#11998e", "#38ef7d"] },
];

export function HeroTools() {
  const [tab, setTab] = useState<"ai" | "xiaok">("ai");

  return (
    <div className="mt-7">
      <div className="mx-auto flex w-fit items-center gap-1 rounded-full border border-border bg-surface p-1 shadow-sm">
        <button
          type="button"
          onClick={() => setTab("ai")}
          className={cn(
            "rounded-full px-6 py-1.5 text-sm font-medium transition",
            tab === "ai"
              ? "brand-gradient text-white shadow"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          AI工具
        </button>
        <button
          type="button"
          onClick={() => setTab("xiaok")}
          className={cn(
            "rounded-full px-6 py-1.5 text-sm font-medium transition",
            tab === "xiaok"
              ? "brand-gradient text-white shadow"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          小k
        </button>
      </div>

      {tab === "ai" ? (
        <div className="mt-8 flex justify-center gap-5 overflow-x-auto pb-2">
          {TOOLS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.label}
                type="button"
                className="group flex w-24 shrink-0 flex-col items-center gap-2.5"
              >
                <div
                  className="relative flex h-[88px] w-[88px] items-center justify-center rounded-2xl text-white shadow-sm transition group-hover:-translate-y-0.5 group-hover:shadow-md"
                  style={{
                    backgroundImage: `linear-gradient(135deg, ${t.grad[0]}, ${t.grad[1]})`,
                  }}
                >
                  <Icon className="h-8 w-8" />
                  {t.badge && (
                    <span className="absolute -right-1.5 -top-1.5 rounded-full bg-brand px-1.5 py-0.5 text-[10px] font-semibold text-white shadow">
                      {t.badge}
                    </span>
                  )}
                </div>
                <span className="text-center text-sm text-foreground">
                  {t.label}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="mt-12 text-center text-sm text-muted">
          小 k 智能助手 — 敬请期待
        </div>
      )}
    </div>
  );
}
