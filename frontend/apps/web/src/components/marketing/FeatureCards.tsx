import { ArrowRight } from "lucide-react";
import { FEATURE_CARDS } from "@/lib/marketing";
import { IconChip, type Tone } from "./shared";

export function FeatureCards() {
  return (
    <div className="relative z-10 grid grid-cols-1 gap-5 pb-4 sm:grid-cols-2 lg:grid-cols-4">
      {FEATURE_CARDS.map((c) => (
        <div
          key={c.title}
          className="group ink-card p-5 transition hover:-translate-y-0.5 hover:shadow-lg"
        >
          <IconChip icon={c.icon} tone={c.tone as Tone} size={48} />
          <h3 className="mt-4 font-display text-lg font-bold text-ink">{c.title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{c.desc}</p>
          <ArrowRight className="mt-4 h-4 w-4 text-muted transition-colors group-hover:text-brand" />
        </div>
      ))}
    </div>
  );
}
