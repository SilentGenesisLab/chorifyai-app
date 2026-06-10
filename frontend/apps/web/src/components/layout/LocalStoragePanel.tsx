"use client";

import { useEffect, useState } from "react";
import { Folder, Loader2, Save } from "lucide-react";

type LocalStorageState = {
  ok: boolean;
  provider: string;
  root: string;
  enabled: boolean;
};

export function LocalStoragePanel() {
  const [state, setState] = useState<LocalStorageState | null>(null);
  const [root, setRoot] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    try {
      const data = await fetch("/api/local-storage", { cache: "no-store" }).then((r) => r.json());
      if (data?.ok) {
        setState(data);
        setRoot(data.root ?? "");
      }
    } catch {
      setMessage("本地路径未连接");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function save() {
    setSaving(true);
    setMessage("");
    try {
      const data = await fetch("/api/local-storage", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ root }),
      }).then((r) => r.json());
      if (!data?.ok) throw new Error(data?.detail ?? data?.error ?? "保存失败");
      setState(data);
      setRoot(data.root ?? root);
      setMessage("已保存");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface-muted/45 p-2.5">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
        <Folder className="h-3.5 w-3.5 text-brand" />
        本地工作路径
      </div>
      <input
        value={root}
        onChange={(event) => setRoot(event.target.value)}
        placeholder="选择或输入本地路径"
        className="mb-2 w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[11px] text-foreground outline-none focus:border-brand/50"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={save}
          disabled={saving || !root.trim()}
          className="flex items-center gap-1 rounded-md bg-brand px-2 py-1.5 text-[11px] font-medium text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
          保存
        </button>
        <span className="min-w-0 flex-1 truncate text-[11px] text-muted">
          {message || (state?.enabled ? "上传/合成写入本地" : `当前: ${state?.provider ?? "unknown"}`)}
        </span>
      </div>
    </div>
  );
}
