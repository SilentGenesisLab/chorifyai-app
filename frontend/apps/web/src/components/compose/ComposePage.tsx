"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProjectRow, type ComposeProject } from "./ProjectRow";
import { NewProjectFlow } from "./NewProjectFlow";

const TABS = [
  { key: "smart_mix", label: "智能混剪（经典版）" },
  { key: "super_mix", label: "超级混剪Pro" },
  { key: "one_click", label: "一键成片" },
];

export function ComposePage() {
  const [tab, setTab] = useState("smart_mix");
  const [projects, setProjects] = useState<ComposeProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [flowOpen, setFlowOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: tab });
      if (q.trim()) params.set("q", q.trim());
      const res = await fetch(`/api/projects?${params.toString()}`);
      const data = await res.json();
      if (data.ok) setProjects(data.projects);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [tab, q]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="min-h-full pb-10">
      {/* banner */}
      <div
        className="relative mx-6 mt-6 flex h-28 items-center justify-center overflow-hidden rounded-2xl"
        style={{ backgroundImage: "linear-gradient(100deg, #103230, #15233f 52%, #2c2152)" }}
      >
        <button
          type="button"
          onClick={() => setFlowOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-5 py-2.5 text-[15px] font-semibold text-white backdrop-blur transition hover:bg-white/20"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-white text-ink">
            <Plus className="h-4 w-4" />
          </span>
          新建量产工程
        </button>
      </div>

      {/* tabs + search */}
      <div className="mx-6 mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-sm font-medium transition",
                tab === t.key
                  ? "bg-surface-muted text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="输入关键词"
            className="h-9 w-56 rounded-lg border border-border bg-surface pl-8 pr-3 text-sm outline-none focus:border-brand"
          />
        </div>
      </div>

      {/* list */}
      <div className="mx-6 mt-2 divide-y divide-border border-t border-border">
        {loading ? (
          <p className="py-20 text-center text-sm text-muted">加载中…</p>
        ) : projects.length === 0 ? (
          <p className="py-20 text-center text-sm text-muted">
            暂无工程，点击「新建量产工程」开始
          </p>
        ) : (
          projects.map((p) => (
            <ProjectRow key={p.id} project={p} onChanged={load} />
          ))
        )}
      </div>
      {!loading && projects.length > 0 && (
        <p className="py-8 text-center text-xs text-muted">已经到底啦</p>
      )}

      <NewProjectFlow open={flowOpen} onClose={() => setFlowOpen(false)} />
    </div>
  );
}
