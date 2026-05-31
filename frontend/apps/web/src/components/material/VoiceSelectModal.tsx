"use client";

import { useEffect, useMemo, useState } from "react";
import { X, Check, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { tileGradient, type Voice } from "./types";
import { Dropdown } from "./Dropdown";

const CATS = ["推荐", "方言", "语种", "风格"];
const GENDERS = [
  { k: "all", l: "全部" },
  { k: "male", l: "男声" },
  { k: "female", l: "女声" },
  { k: "child", l: "童声" },
  { k: "elder", l: "老人声" },
];
const DIALECTS = [
  "全部", "粤语", "东北", "重庆", "广西", "河南", "台湾", "青岛", "天津", "陕西", "四川", "北京",
];
const EMOTIONS = ["默认", "开心", "平和", "伤心", "愤怒", "惊讶"];

export function VoiceSelectModal({
  open,
  value,
  emotion,
  onClose,
  onConfirm,
}: {
  open: boolean;
  value?: string;
  emotion: string;
  onClose: () => void;
  onConfirm: (voice: Voice, emotion: string) => void;
}) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [cat, setCat] = useState("推荐");
  const [gender, setGender] = useState("all");
  const [dialect, setDialect] = useState("全部");
  const [emo, setEmo] = useState(emotion || "默认");
  const [selectedId, setSelectedId] = useState<string | undefined>(value);

  useEffect(() => {
    if (!open) return;
    setSelectedId(value);
    setEmo(emotion || "默认");
    fetch("/api/voice/voices")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) setVoices(d.voices);
      })
      .catch(() => {});
  }, [open, value, emotion]);

  const filtered = useMemo(() => {
    let v = voices;
    if (gender === "male") v = v.filter((x) => x.gender === "male");
    else if (gender === "female") v = v.filter((x) => x.gender === "female");
    else if (gender === "child" || gender === "elder") v = [];

    if (cat === "方言") {
      v = v.filter((x) =>
        /方言|粤语|东北|重庆|广西|河南|台湾|青岛|天津|陕西|四川|北京/.test(x.langDialect),
      );
      if (dialect !== "全部") v = v.filter((x) => x.langDialect.includes(dialect));
    } else if (cat === "语种") {
      v = v.filter((x) => /语种|日文|英|韩|印尼|西班牙|泰|越|俄|法|德/.test(x.langDialect));
    } else if (cat === "风格") {
      v = v.filter((x) => x.scene && x.scene !== "通用场景");
    }
    return v;
  }, [voices, cat, gender, dialect]);

  if (!open) return null;
  const selected = voices.find((x) => x.id === selectedId);

  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/40">
      <div className="flex h-full w-[1000px] max-w-[94vw] flex-col bg-surface text-foreground">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold">选择音色</h2>
          <button type="button" onClick={onClose} className="text-muted hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 pt-3 text-xs text-muted">
          当前供应商：<span className="font-medium text-brand">豆包</span> · 更多即将支持（MiniMax / ElevenLabs）
        </div>

        <div className="flex items-center gap-5 border-b border-border px-6 py-3">
          {CATS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCat(c)}
              className={cn(
                "text-[15px] transition",
                cat === c ? "font-semibold text-brand" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {c}
            </button>
          ))}
          <div className="ml-auto">
            <Dropdown
              label="情感:"
              value={emo}
              options={EMOTIONS.map((e) => ({ value: e }))}
              onChange={setEmo}
              align="end"
            />
          </div>
        </div>

        <div className="space-y-2 px-6 py-3">
          <div className="flex flex-wrap gap-2">
            {GENDERS.map((g) => (
              <Chip key={g.k} active={gender === g.k} onClick={() => setGender(g.k)}>
                {g.l}
              </Chip>
            ))}
          </div>
          {cat === "方言" && (
            <div className="flex flex-wrap gap-2">
              {DIALECTS.map((d) => (
                <Chip key={d} active={dialect === d} onClick={() => setDialect(d)} small>
                  {d}
                </Chip>
              ))}
            </div>
          )}
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-2 content-start gap-3 overflow-y-auto px-6 py-2">
          {filtered.length === 0 ? (
            <p className="col-span-2 py-16 text-center text-sm text-muted">该分类暂无音色</p>
          ) : (
            filtered.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => setSelectedId(v.id)}
                className={cn(
                  "flex items-center gap-3 rounded-xl border-2 p-3 text-left transition",
                  selectedId === v.id
                    ? "border-brand bg-brand-soft/40"
                    : "border-border hover:bg-surface-muted",
                )}
              >
                <span
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
                  style={{ backgroundImage: tileGradient(v.id) }}
                >
                  {v.name.charAt(0)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {v.name}
                  </span>
                  <span className="block truncate text-xs text-muted">
                    {v.scene || (v.gender === "male" ? "男声" : "女声")}
                  </span>
                </span>
                {selectedId === v.id && <Check className="h-4 w-4 shrink-0 text-brand" />}
              </button>
            ))
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-3">
          <span className="mr-auto text-sm text-muted">共 {filtered.length} 个音色</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border bg-surface px-5 py-2 text-sm transition hover:bg-surface-muted"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => selected && onConfirm(selected, emo)}
            disabled={!selected}
            className="brand-gradient rounded-lg px-6 py-2 text-sm font-semibold text-white shadow-seal transition hover:opacity-90 disabled:opacity-50"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  small,
  children,
}: {
  active: boolean;
  onClick: () => void;
  small?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border transition",
        small ? "px-3 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
        active
          ? "border-brand bg-brand-soft text-brand"
          : "border-border bg-surface text-foreground hover:bg-surface-muted",
      )}
    >
      {children}
    </button>
  );
}
