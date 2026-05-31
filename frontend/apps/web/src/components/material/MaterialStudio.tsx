"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LayoutGrid, List } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  MATERIAL_TABS,
  type MaterialTab,
  type GenJob,
  type ResultKind,
  type GeneratePayload,
  type VoiceGeneratePayload,
  type TranslatePayload,
  type TranslateResult,
  type ClonePayload,
} from "./types";

const MATERIAL_TAB_KEYS: MaterialTab[] = [
  "ai_studio",
  "replica",
  "element_swap",
  "dubbing",
  "digital_human",
];

type PersistInput = {
  module: string;
  kind: ResultKind;
  text?: string;
  voiceName?: string;
  resultUrl?: string | null;
  thumbnailUrl?: string | null;
  durationSec?: number | null;
};
import { Dropdown } from "./Dropdown";
import { AiStudioPanel } from "./AiStudioPanel";
import { ReplicaPanel } from "./ReplicaPanel";
import { ElementSwapPanel } from "./ElementSwapPanel";
import { DubbingPanel } from "./DubbingPanel";
import { DigitalHumanPanel } from "./DigitalHumanPanel";
import { ResultsPanel } from "./ResultsPanel";

export function MaterialStudio() {
  const [tab, setTab] = useState<MaterialTab>("ai_studio");
  const [view, setView] = useState<"grid" | "list">("grid");
  // 真实数据：进入页面从 PG 拉取历史生成回显（不再用 mock 种子）
  const [results, setResults] = useState<GenJob[]>([]);
  const [typeFilter, setTypeFilter] = useState("全部");
  const [funcFilter, setFuncFilter] = useState("全部");
  const pollers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  useEffect(() => {
    const map = pollers.current;
    return () => Object.values(map).forEach(clearInterval);
  }, []);

  // 进入素材生产：从 PG 拉取真实历史生成（/api/generations）回显到右侧列表
  useEffect(() => {
    let alive = true;
    fetch("/api/generations")
      .then((r) => r.json())
      .then((d) => {
        if (!alive || !d?.ok) return;
        const mapped: GenJob[] = (d.generations ?? []).map(
          (g: {
            id: string;
            type: string;
            kind: string;
            resultUrl?: string | null;
            thumbnailUrl?: string | null;
            durationSec?: number | null;
            createdAt: string;
          }) => ({
            id: g.id,
            type: (MATERIAL_TAB_KEYS.includes(g.type as MaterialTab)
              ? g.type
              : "dubbing") as MaterialTab,
            status: "succeeded" as const,
            kind: g.kind as ResultKind,
            resultUrl: g.resultUrl,
            thumbnailUrl: g.thumbnailUrl,
            durationSec: g.durationSec ?? undefined,
            createdAt: g.createdAt,
          }),
        );
        setResults(mapped);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // 持久化一条成功生成到 PG（失败静默，不阻塞前端展示）
  const persistGen = useCallback((g: PersistInput) => {
    fetch("/api/generations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(g),
    }).catch(() => {});
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

  // Real Doubao TTS (synchronous) — backend assembles MP3 → OSS → public URL.
  const onVoiceGenerate = useCallback(async (p: VoiceGeneratePayload) => {
    const id = `tts_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const job: GenJob = {
      id,
      type: "dubbing",
      status: "processing",
      kind: "audio",
      progress: 40,
      durationSec: Math.max(2, Math.round(p.text.length * 0.24)),
      createdAt: new Date().toISOString(),
    };
    setResults((prev) => [job, ...prev]);
    try {
      const res = await fetch("/api/voice/tts", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: p.text, speaker: p.speaker, emotion: p.emotion }),
      });
      const data = await res.json();
      setResults((prev) =>
        prev.map((j) =>
          j.id === id
            ? data.ok
              ? { ...j, status: "succeeded", progress: 100, resultUrl: data.url }
              : { ...j, status: "failed" }
            : j,
        ),
      );
      if (data.ok)
        persistGen({
          module: "dubbing",
          kind: "audio",
          text: p.text,
          voiceName: p.voiceName,
          resultUrl: data.url,
          durationSec: job.durationSec,
        });
    } catch {
      setResults((prev) =>
        prev.map((j) => (j.id === id ? { ...j, status: "failed" } : j)),
      );
    }
  }, [persistGen]);

  // 语音翻译：ASR + 翻译（可选用所选音色合成译文音频）。
  // 返回 sourceText/text 供面板内联展示；选了音色才产出右侧音频卡。
  const onTranslate = useCallback(
    async (p: TranslatePayload): Promise<TranslateResult> => {
      const id = p.speaker
        ? `tr_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
        : null;
      if (id) {
        const job: GenJob = {
          id,
          type: "dubbing",
          status: "processing",
          kind: "audio",
          progress: 40,
          createdAt: new Date().toISOString(),
        };
        setResults((prev) => [job, ...prev]);
      }
      try {
        const res = await fetch("/api/voice/translate", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            audio_url: p.audioUrl,
            text: p.text,
            source: p.source,
            target: p.target,
            speaker: p.speaker,
          }),
        });
        const d = await res.json();
        if (id) {
          setResults((prev) =>
            prev.map((j) =>
              j.id === id
                ? d.ok && d.url
                  ? { ...j, status: "succeeded", progress: 100, resultUrl: d.url }
                  : { ...j, status: "failed" }
                : j,
            ),
          );
        }
        if (id && d.ok && d.url)
          persistGen({
            module: "translate",
            kind: "audio",
            text: d.text,
            voiceName: p.voiceName,
            resultUrl: d.url,
          });
        return d.ok
          ? { ok: true, sourceText: d.sourceText, text: d.text, url: d.url }
          : { ok: false };
      } catch {
        if (id)
          setResults((prev) =>
            prev.map((j) => (j.id === id ? { ...j, status: "failed" } : j)),
          );
        return { ok: false };
      }
    },
    [persistGen],
  );

  // 语音克隆（VoxCPM）：参考音 + 文本 → 克隆音频卡。
  const onClone = useCallback(async (p: ClonePayload) => {
    const id = `cl_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const job: GenJob = {
      id,
      type: "dubbing",
      status: "processing",
      kind: "audio",
      progress: 30,
      createdAt: new Date().toISOString(),
    };
    setResults((prev) => [job, ...prev]);
    try {
      const res = await fetch("/api/voice/clone", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text: p.text,
          reference_url: p.referenceUrl,
          ultimate: p.ultimate,
          prompt_text: p.promptText,
        }),
      });
      const d = await res.json();
      setResults((prev) =>
        prev.map((j) =>
          j.id === id
            ? d.ok
              ? { ...j, status: "succeeded", progress: 100, resultUrl: d.url }
              : { ...j, status: "failed" }
            : j,
        ),
      );
      if (d.ok)
        persistGen({
          module: "clone",
          kind: "audio",
          text: p.text,
          resultUrl: d.url,
        });
    } catch {
      setResults((prev) =>
        prev.map((j) => (j.id === id ? { ...j, status: "failed" } : j)),
      );
    }
  }, [persistGen]);

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
          {tab === "dubbing" && (
            <DubbingPanel
              onVoiceGenerate={onVoiceGenerate}
              onTranslate={onTranslate}
              onClone={onClone}
            />
          )}
          {tab === "digital_human" && <DigitalHumanPanel onGenerate={onGenerate} />}
        </div>
        <div className="min-w-0 flex-1 overflow-y-auto">
          <ResultsPanel results={results} view={view} />
        </div>
      </div>
    </div>
  );
}
