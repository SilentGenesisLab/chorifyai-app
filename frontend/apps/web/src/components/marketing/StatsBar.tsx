import { Users, Layers, ShieldCheck } from "lucide-react";
import { STATS } from "@/lib/marketing";

const ICONS = [Users, Layers, ShieldCheck];

export function StatsBar() {
  return (
    <div className="relative z-10 mt-8 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 rounded-2xl border border-border bg-surface/70 px-8 py-5 backdrop-blur">
      {STATS.map((s, i) => {
        const Icon = ICONS[i] ?? Users;
        return (
          <div key={s.label} className="flex items-center gap-3">
            <Icon className="h-5 w-5 text-brand" strokeWidth={1.7} />
            <span className="font-display text-xl font-bold text-ink">{s.value}</span>
            <span className="text-sm text-muted-foreground">{s.label}</span>
            {i < STATS.length - 1 && (
              <span className="ml-6 hidden h-8 w-px bg-border sm:block" />
            )}
          </div>
        );
      })}
    </div>
  );
}
