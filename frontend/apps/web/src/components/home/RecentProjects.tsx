import { ChevronDown } from "lucide-react";
import { ProjectCard, type RecentProject } from "./ProjectCard";

export function RecentProjects({ projects }: { projects: RecentProject[] }) {
  return (
    <section className="mt-12">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">最近工程</h2>
        <span className="flex items-center gap-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-muted-foreground">
          全部类型
          <ChevronDown className="h-4 w-4 text-muted" />
        </span>
      </div>

      {projects.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted">
          暂无工程，去「合成量产」新建一个吧
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-5">
          {projects.map((p, i) => (
            <ProjectCard key={p.id} project={p} index={i} />
          ))}
        </div>
      )}
    </section>
  );
}
