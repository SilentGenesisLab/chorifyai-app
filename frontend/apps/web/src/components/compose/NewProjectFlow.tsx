"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { X, Clapperboard, Wand2, Sparkles, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Mode = "smart_mix" | "super_mix" | "one_click";

const MODES: {
  key: Mode;
  title: string;
  desc: string;
  icon: typeof Clapperboard;
  badge?: string;
  grad: [string, string];
}[] = [
  { key: "smart_mix", title: "智能混剪（经典版）", desc: "经典模式，功能齐全", icon: Clapperboard, grad: ["#6d3bce", "#3a1d6e"] },
  { key: "super_mix", title: "超级混剪Pro", desc: "简单易上手，解锁更强创造力", icon: Wand2, badge: "Pro", grad: ["#3a3f8f", "#1d2350"] },
  { key: "one_click", title: "AI一键成片", desc: "输入素材和关键词，AI 自动剪辑出片", icon: Sparkles, grad: ["#9e2d5a", "#5a1d3a"] },
];

const RATIOS: { key: string; label: string; sizes: [number, number][] }[] = [
  { key: "9:16", label: "竖版 9:16", sizes: [[1080, 1920], [720, 1280]] },
  { key: "3:4", label: "竖版 3:4", sizes: [[1080, 1440], [720, 960]] },
  { key: "16:9", label: "横版 16:9", sizes: [[1920, 1080], [1280, 720]] },
  { key: "4:3", label: "横版 4:3", sizes: [[1440, 1080], [960, 720]] },
  { key: "1:1", label: "方形 1:1", sizes: [[1080, 1080], [720, 720]] },
];

function defaultName() {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `新建视频${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}-${p(d.getMinutes())}`;
}

export function NewProjectFlow({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode | null>(null);
  const [name, setName] = useState("");
  const [ratioIdx, setRatioIdx] = useState(0);
  const [sizeIdx, setSizeIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setMode(null);
      setName(defaultName());
      setRatioIdx(0);
      setSizeIdx(0);
      setErr(null);
    }
  }, [open]);

  const ratio = RATIOS[ratioIdx];
  const [w, h] = useMemo(() => ratio.sizes[sizeIdx] ?? ratio.sizes[0], [ratio, sizeIdx]);

  if (!open) return null;

  async function create() {
    if (!mode) return;
    if (!name.trim()) {
      setErr("请输入工程名称");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim(), type: mode, width: w, height: h }),
      });
      const data = await res.json();
      if (!data.ok) {
        setErr(data.error || "创建失败");
        return;
      }
      router.push(`/editor/${data.project.id}`);
    } catch {
      setErr("网络错误，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      {mode === null ? (
        // ---- 图2: mode picker ----
        <div className="relative w-full max-w-4xl">
          <button
            type="button"
            onClick={onClose}
            className="absolute -top-10 right-0 text-white/80 hover:text-white"
          >
            <X className="h-6 w-6" />
          </button>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            {MODES.map((m) => {
              const Icon = m.icon;
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setMode(m.key)}
                  className="ink-card group overflow-hidden p-0 text-left transition hover:-translate-y-1"
                >
                  <div
                    className="relative flex h-40 items-center justify-center"
                    style={{ backgroundImage: `linear-gradient(135deg, ${m.grad[0]}, ${m.grad[1]})` }}
                  >
                    <Icon className="h-12 w-12 text-white/90" />
                  </div>
                  <div className="p-5">
                    <h3 className="flex items-center gap-2 font-display text-lg font-bold text-ink">
                      {m.title}
                      {m.badge && (
                        <span className="rounded-full bg-brand px-1.5 py-0.5 text-[10px] font-semibold text-white">
                          {m.badge}
                        </span>
                      )}
                    </h3>
                    <p className="mt-1.5 text-sm text-muted-foreground">{m.desc}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        // ---- 图3: new video modal ----
        <div className="w-full max-w-xl rounded-2xl bg-surface p-7 shadow-xl">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-foreground">新建视频工程</h2>
            <button type="button" onClick={onClose} className="text-muted hover:text-foreground">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="mt-6 space-y-5">
            <Field label="工程名称">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-11 w-full rounded-lg border border-border bg-surface px-3.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
              />
            </Field>

            <Field label="选择比例">
              <div className="flex flex-wrap gap-2.5">
                {RATIOS.map((r, i) => (
                  <Chip
                    key={r.key}
                    active={ratioIdx === i}
                    onClick={() => {
                      setRatioIdx(i);
                      setSizeIdx(0);
                    }}
                  >
                    {r.label}
                  </Chip>
                ))}
                <Chip active={false} onClick={() => {}} disabled>
                  自定义尺寸
                </Chip>
              </div>
            </Field>

            <Field label="选择尺寸">
              <div className="flex flex-wrap gap-2.5">
                {ratio.sizes.map((s, i) => (
                  <Chip key={i} active={sizeIdx === i} onClick={() => setSizeIdx(i)}>
                    {s[0]}x{s[1]}
                  </Chip>
                ))}
              </div>
            </Field>

            <Field label="保存位置">
              <div className="flex h-11 items-center rounded-lg border border-border bg-surface px-3.5 text-sm text-muted">
                选择文件夹（可选）
              </div>
            </Field>

            {err && <p className="text-sm text-brand">{err}</p>}
          </div>

          <div className="mt-7 flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setMode(null)}
              className="rounded-lg border border-border bg-surface px-5 py-2 text-sm text-foreground transition hover:bg-surface-muted"
            >
              取消
            </button>
            <button
              type="button"
              onClick={create}
              disabled={busy}
              className="brand-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-60"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              确定
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-foreground">
        {label} <span className="text-brand">*</span>
      </p>
      {children}
    </div>
  );
}

function Chip({
  active,
  onClick,
  disabled,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-lg border px-4 py-2 text-sm transition",
        active
          ? "border-brand bg-brand-soft text-brand"
          : "border-border bg-surface text-foreground hover:bg-surface-muted",
        disabled && "cursor-not-allowed opacity-50 hover:bg-surface",
      )}
    >
      {children}
    </button>
  );
}
