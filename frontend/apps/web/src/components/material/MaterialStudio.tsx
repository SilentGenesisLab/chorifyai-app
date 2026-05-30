"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LayoutGrid, List } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  MATERIAL_TABS,
  type MaterialTab,
  type GenJob,
  type GeneratePayload,
} from "./types";
import { Dropdown } from "./Dropdown";
import { AiStudioPanel } from "./AiStudioPanel";
import { ReplicaPanel } from "./ReplicaPanel";
import { ElementSwapPanel } from "./ElementSwapPanel";
import { DubbingPanel } from "./DubbingPanel";
import { DigitalHumanPanel } from "./DigitalHumanPanel";
import { ResultsPanel } from "./ResultsPanel";

const SEED_RESULTS: GenJob[] = [
  {
    id: "seed_audio_1",
    type: "dubbing",
    status: "succeeded",
    kind: "audio",
    durationSec: 27,
    createdAt: "2026-05-31T02:22:15",
  },
  {
    id: "seed_audio_2",
    type: "dubbing",
    status: "succeeded",
    kind: "audio",
    durationSec: 2,
    createdAt: "2026-05-31T02:21:49",
  },
  {
    id: "seed_video_1",
    type: "digital_human",
    status: "succeeded",
    kind: "video",
    thumbnailUrl: "/illus_people.webp",
    durationSec: 5,
    createdAt: "2026-05-30T23:25:44",
  },
];

export function MaterialStudio() {
  const [tab, setTab] = useState<MaterialTab>("ai_studio");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [results, setResults] = useState<GenJob[]>(SEED_RESULTS);
  const [typeFilter, setTypeFilter] = useState("全部");
  const [funcFilter, setFuncFilter] = useState("全部");
  const pollers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  useEffect(() => {
    const map = pollers.current;
    return () => Object.values(map).forEach(clearInterval);
  }, []);

  const onGenerate = useCallback(
    async (payload: GeneratePayload) => {
      const res = await fetch("/api/material/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          tab,
          settings: payload.settings,
          source_url: payload.sourceUrl,
          refs: payload.refs,
          prompt: payload.prompt,
          voice: payload.voice,
          ip: payload.ip,
        }),
      });
      const data = await res.json();
      if (!data?.ok) return;

      const kind = tab === "dubbing" ? "audio" : "video";
      const job: GenJob = {
        ...data.job,
        kind,
        thumbnailUrl: null,
        durationSec: payload.durationSec,
      };
      setResults((prev) => [job, ...prev]);

      const id: string = job.id;
      const tick = async () => {
        try {
          const r = await fetch(`/api/material/jobs/${id}`);
          const d = await r.json();
          if (!d?.ok) return;
          setResults((prev) =>
            prev.map((j) => (j.id === id ? { ...j, ...d.job } : j)),
          );
          if (d.job.status === "succeeded" || d.job.status === "failed") {
            clearInterval(pollers.current[id]);
            delete pollers.current[id];
          }
        } catch {
          /* keep polling */
        }
      };
      pollers.current[id] = setInterval(tick, 1000);
      tick();
    },
    [tab],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-surface/60 px-6">
        <div className="-mb-px flex items-center gap-1">
          {MATERIAL_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                "border-b-2 px-3.5 py-3.5 text-[15px] font-medium transition",
                tab === t.key
                  ? "border-brand text-brand"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Dropdown
            label="类型:"
            value={typeFilter}
            options={["全部", "图片", "视频", "音频"].map((v) => ({ value: v }))}
            onChange={setTypeFilter}
            align="end"
          />
          <Dropdown
            label="功能:"
            value={funcFilter}
            options={["全部", "AI影棚", "数字人", "配音"].map((v) => ({ value: v }))}
            onChange={setFuncFilter}
            align="end"
          />
          <span className="ml-1 hidden text-xs text-muted xl:inline">
            内容由AI生成
          </span>
          <div className="flex items-center rounded-lg border border-border bg-surface p-0.5">
            <button
              type="button"
              onClick={() => setView("grid")}
              className={cn(
                "rounded-md p-1.5 transition",
                view === "grid" ? "bg-surface-muted text-brand" : "text-muted",
              )}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setView("list")}
              className={cn(
                "rounded-md p-1.5 transition",
                view === "list" ? "bg-surface-muted text-brand" : "text-muted",
              )}
            >
              <List className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="w-[540px] shrink-0 overflow-y-auto border-r border-border">
          {tab === "ai_studio" && <AiStudioPanel onGenerate={onGenerate} />}
          {tab === "replica" && <ReplicaPanel onGenerate={onGenerate} />}
          {tab === "element_swap" && <ElementSwapPanel onGenerate={onGenerate} />}
          {tab === "dubbing" && <DubbingPanel onGenerate={onGenerate} />}
          {tab === "digital_human" && <DigitalHumanPanel onGenerate={onGenerate} />}
        </div>
        <div className="min-w-0 flex-1 overflow-y-auto">
          <ResultsPanel results={results} view={view} />
        </div>
      </div>
    </div>
  );
}
