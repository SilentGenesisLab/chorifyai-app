"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  MoreVertical,
  LayoutGrid,
  Edit3,
  Pencil,
  Copy,
  CopyPlus,
  FolderInput,
  Trash2,
} from "lucide-react";
import { cn, formatDateTime } from "@/lib/utils";
import { tileGradient } from "@/components/material/types";

export type ComposeProject = {
  id: string;
  name: string;
  type: string;
  width: number;
  height: number;
  comboCount: number;
  coverUrl: string | null;
  creator: string;
  updatedAt: string;
};

const TYPE_TAG: Record<string, string> = {
  SMART_MIX: "混剪",
  SUPER_MIX: "混剪Pro",
  ONE_CLICK: "成片",
};

export function ProjectRow({
  project,
  onChanged,
}: {
  project: ComposeProject;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [menu, setMenu] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menu]);

  const open = () => router.push(`/editor/${project.id}`);

  async function rename() {
    setMenu(false);
    const name = window.prompt("重命名工程", project.name);
    if (name && name.trim() && name.trim() !== project.name) {
      await fetch(`/api/projects/${project.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      onChanged();
    }
  }

  async function del() {
    setMenu(false);
    if (window.confirm(`确定删除工程「${project.name}」？`)) {
      await fetch(`/api/projects/${project.id}`, { method: "DELETE" });
      onChanged();
    }
  }

  const stub = () => setMenu(false);

  const MENU = [
    { icon: LayoutGrid, label: "瀑布流", onClick: stub },
    { icon: Edit3, label: "编辑", onClick: open },
    { icon: Pencil, label: "重命名", onClick: rename },
    { icon: Copy, label: "复制", onClick: stub },
    { icon: CopyPlus, label: "复制到", onClick: stub },
    { icon: FolderInput, label: "移动到", onClick: stub },
    { icon: Trash2, label: "删除", onClick: del, danger: true },
  ];

  return (
    <div className="group flex items-center gap-4 py-4">
      <button
        type="button"
        onClick={open}
        className="relative h-24 w-40 shrink-0 overflow-hidden rounded-xl border border-border"
        style={{ backgroundImage: tileGradient(project.id) }}
      >
        <span className="absolute left-2 top-2 rounded bg-black/35 px-1.5 py-0.5 text-[10px] text-white backdrop-blur">
          {TYPE_TAG[project.type] ?? "混剪"}
        </span>
      </button>

      <div className="min-w-0 flex-1 cursor-pointer" onClick={open}>
        <h3 className="truncate text-[15px] font-semibold text-foreground">
          {project.name}
        </h3>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded bg-surface-muted px-1.5 py-0.5 text-muted-foreground">
            {project.creator || "我"}创建
          </span>
          <span className="rounded bg-surface-muted px-1.5 py-0.5 text-muted-foreground">
            尺寸: {project.width}x{project.height}
          </span>
        </div>
        <p className="mt-2 text-xs text-muted">
          最后编辑于 {formatDateTime(project.updatedAt)}
        </p>
      </div>

      <div className="hidden shrink-0 text-center sm:block">
        <p className="text-xl font-semibold text-foreground">{project.comboCount}</p>
        <p className="text-xs text-muted">视频组合数</p>
      </div>

      <div className="relative shrink-0" ref={ref}>
        <button
          type="button"
          onClick={() => setMenu((o) => !o)}
          className="rounded-lg p-1.5 text-muted transition hover:bg-surface-muted hover:text-foreground"
        >
          <MoreVertical className="h-5 w-5" />
        </button>
        {menu && (
          <div className="absolute right-0 top-full z-30 mt-1 w-36 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-lg">
            {MENU.map((m) => {
              const Icon = m.icon;
              return (
                <button
                  key={m.label}
                  type="button"
                  onClick={m.onClick}
                  className={cn(
                    "flex w-full items-center gap-2.5 px-3 py-2 text-sm transition hover:bg-surface-muted",
                    m.danger ? "text-brand" : "text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 text-muted" />
                  {m.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
