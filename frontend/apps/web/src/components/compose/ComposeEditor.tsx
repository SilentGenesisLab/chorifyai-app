"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  Plus,
  FolderPlus,
  Rocket,
  Film,
  Image as ImageIcon,
  Music,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { tileGradient } from "@/components/material/types";
import { MaterialPicker, type PickedAsset } from "./MaterialPicker";

export function ComposeEditor({
  project,
}: {
  project: { id: string; name: string; width: number; height: number };
}) {
  const router = useRouter();
  const [pickerOpen, setPickerOpen] = useState(true);
  const [materials, setMaterials] = useState<PickedAsset[]>([]);
  const [rail, setRail] = useState<"video" | "image" | "audio">("video");

  const onConfirm = (picked: PickedAsset[]) => {
    setMaterials((m) => {
      const ids = new Set(m.map((x) => x.id));
      return [...m, ...picked.filter((p) => !ids.has(p.id))];
    });
    setPickerOpen(false);
  };

  const matchRail = (a: PickedAsset) => {
    const t = a.type.toLowerCase();
    if (rail === "image") return t === "image";
    if (rail === "audio") return t === "audio";
    return t !== "image" && t !== "audio";
  };
  const railItems = materials.filter(matchRail);

  const RAILS = [
    { k: "video", l: "视频", I: Film },
    { k: "image", l: "图片", I: ImageIcon },
    { k: "audio", l: "音频", I: Music },
  ] as const;

  return (
    <div className="flex h-screen flex-col bg-[#0d0d11] text-white/90">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-white/10 px-4">
        <button
          type="button"
          onClick={() => router.push("/compose")}
          className="text-white/70 transition hover:text-white"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="font-display text-lg font-bold tracking-tight text-white">
          {BRAND.name}
        </span>
        <span className="max-w-[200px] truncate text-sm text-white/45">
          / {project.name}
        </span>
        <div className="ml-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm transition hover:bg-white/15"
          >
            <Plus className="h-4 w-4" />
            导入素材原料
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm transition hover:bg-white/15"
          >
            <FolderPlus className="h-4 w-4" />
            导入镜头分组
          </button>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="rounded-lg bg-white/10 px-3 py-1.5 text-sm">素材调试</span>
          <button
            type="button"
            className="brand-gradient flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium text-white"
          >
            <Rocket className="h-4 w-4" />
            极速裂变
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[320px] shrink-0 flex-col border-r border-white/10">
          <div className="flex items-center gap-1 border-b border-white/10 px-3 py-2 text-sm">
            {RAILS.map((t) => {
              const Icon = t.I;
              return (
                <button
                  key={t.k}
                  type="button"
                  onClick={() => setRail(t.k)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 transition",
                    rail === t.k
                      ? "bg-white/10 text-white"
                      : "text-white/55 hover:text-white",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {t.l}
                </button>
              );
            })}
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {railItems.length === 0 ? (
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="flex h-40 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 text-white/45 transition hover:border-white/30 hover:text-white/70"
              >
                <Plus className="h-6 w-6" />
                <span className="text-sm">导入素材原料</span>
              </button>
            ) : (
              <div className="grid grid-cols-2 gap-2.5">
                {railItems.map((a) => (
                  <div
                    key={a.id}
                    className="relative aspect-[3/4] overflow-hidden rounded-lg"
                    style={{ backgroundImage: tileGradient(a.id) }}
                  >
                    {a.thumbnailUrl && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={a.thumbnailUrl}
                        alt=""
                        className="absolute inset-0 h-full w-full object-cover"
                      />
                    )}
                    <span className="absolute inset-x-0 bottom-0 truncate bg-black/45 px-1.5 py-0.5 text-[10px] text-white">
                      {a.name}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>

        <main className="flex flex-1 flex-col items-center justify-center gap-3 bg-[#08080b] text-white/40">
          <div
            className="flex items-center justify-center rounded-xl border border-white/10"
            style={{
              height: "44vh",
              aspectRatio: `${project.width} / ${project.height}`,
            }}
          >
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex flex-col items-center gap-1.5 text-white/40 transition hover:text-white/75"
            >
              <Plus className="h-7 w-7" />
              <span className="text-xs">导入素材原料</span>
            </button>
          </div>
          <span className="text-xs">
            {project.width} × {project.height}
          </span>
        </main>
      </div>

      <MaterialPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onConfirm={onConfirm}
      />
    </div>
  );
}
