"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Loader2, Wand2 } from "lucide-react";

/**
 * 「AI帮我写」—— 输入提示词，调豆包大模型（后端 /api/voice/write）生成配音文案，
 * 生成后通过 onText 回填到配音文本框。所有 AI 在后端封装。
 */
export function AiWritePopover({
  onText,
  maxChars = 200,
}: {
  onText: (t: string) => void;
  maxChars?: number;
}) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  async function gen() {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/voice/write", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim(), max_chars: maxChars }),
      });
      const d = await res.json();
      if (d.ok && d.text) {
        onText(d.text);
        setOpen(false);
        setPrompt("");
      } else {
        setErr(d.detail || "生成失败，请重试");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "生成失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-violet/15 to-azure/15 px-2.5 py-1 text-xs font-medium text-violet transition hover:from-violet/25 hover:to-azure/25"
      >
        <Sparkles className="h-3.5 w-3.5" />
        AI帮我写
      </button>

      {open && (
        <div className="absolute left-0 top-full z-40 mt-2 w-80 rounded-2xl border border-border bg-surface p-4 shadow-xl">
          <div className="mb-2.5 flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-display font-bold text-ink">
              <Sparkles className="h-4 w-4 text-violet" />
              AI帮我写
              <span className="rounded bg-gradient-to-r from-violet to-azure px-1.5 py-px text-[10px] font-bold text-white">
                New
              </span>
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-muted transition hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            autoFocus
            placeholder="让 AI 帮你写点什么…例如：给一款助眠洋甘菊花茶写一句开场口播"
            className="w-full resize-none rounded-xl border border-border bg-surface-muted/40 p-3 text-sm outline-none transition placeholder:text-muted focus:border-brand/40"
          />
          {err && <p className="mt-1 text-xs text-brand">{err}</p>}

          <div className="mt-3 flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-2 text-xs text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-gradient-to-r from-violet to-azure" />
              豆包
            </span>
            <button
              type="button"
              onClick={gen}
              disabled={busy || !prompt.trim()}
              className="brand-gradient flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-60"
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4" />
              )}
              {busy ? "创作中…" : "创作台词"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
