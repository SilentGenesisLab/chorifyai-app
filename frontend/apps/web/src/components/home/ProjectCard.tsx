import { Boxes } from "lucide-react";
import { formatDateTime } from "@/lib/utils";

const TYPE_LABEL: Record<string, string> = {
  SMART_MIX: "混剪",
  SUPER_MIX: "混剪Pro",
  ONE_CLICK: "成片",
};

const PALETTE: [string, string][] = [
  ["#fde2e4", "#f9a8c4"],
  ["#e7e0ff", "#b8a4ff"],
  ["#fef0d5", "#ffc27a"],
  ["#d8f3dc", "#86d8a8"],
  ["#d0ebff", "#7cc0f5"],
  ["#ffe5ec", "#ff9fb6"],
];

export type RecentProject = {
  id: string;
  name: string;
  type: string;
  comboCount: number;
  updatedAt: string;
};

export function ProjectCard({
  project,
  index,
}: {
  project: RecentProject;
  index: number;
}) {
  const [a, b] = PALETTE[index % PALETTE.length];
  return (
    <div className="group cursor-pointer">
      <div
        className="relative aspect-[4/3] overflow-hidden rounded-xl shadow-sm transition group-hover:shadow-md"
        style={{ backgroundImage: `linear-gradient(135deg, ${a}, ${b})` }}
      >
        <span className="absolute left-2.5 top-2.5 rounded-md bg-black/35 px-2 py-0.5 text-xs font-medium text-white backdrop-blur">
          {TYPE_LABEL[project.type] ?? "混剪"}
        </span>
        <Boxes className="absolute inset-0 m-auto h-10 w-10 text-white/60" />
      </div>
      <h3 className="mt-2.5 truncate text-sm font-semibold text-foreground">
        {project.name}
      </h3>
      <p className="mt-0.5 text-xs text-muted">
        最后编辑于 {formatDateTime(project.updatedAt)}
      </p>
    </div>
  );
}
