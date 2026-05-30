import { ChevronRight, Maximize2, ArrowUp } from "lucide-react";
import { ASSISTANT } from "@/lib/marketing";
import { IconChip, type Tone } from "./shared";

export function AssistantPanel() {
  return (
    <div className="ink-card w-full max-w-md p-4 sm:p-5">
      {/* header */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-brand" />
          <span className="text-sm font-semibold text-ink">{ASSISTANT.title}</span>
          <span className="rounded-md bg-surface-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {ASSISTANT.tag}
          </span>
        </div>
        <Maximize2 className="h-4 w-4 text-muted" />
      </div>

      {/* greeting */}
      <div className="flex items-start gap-2.5 pt-4">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-xs font-bold text-white">
          C
        </span>
        <div>
          <p className="text-sm font-semibold text-ink">{ASSISTANT.greeting}</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {ASSISTANT.intro}
          </p>
        </div>
      </div>

      {/* action rows */}
      <div className="mt-3 space-y-2">
        {ASSISTANT.actions.map((a) => (
          <div
            key={a.title}
            className="flex items-center gap-3 rounded-xl border border-border bg-surface-muted/40 px-3 py-2.5 transition-colors hover:border-brand/30 hover:bg-surface-muted"
          >
            <IconChip icon={a.icon} tone={a.tone as Tone} size={34} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-ink">{a.title}</p>
              <p className="truncate text-[11px] text-muted-foreground">{a.desc}</p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted" />
          </div>
        ))}
      </div>

      {/* input */}
      <div className="mt-4 flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-xs text-muted">
          {ASSISTANT.placeholder}
        </span>
        <button
          type="button"
          aria-label="发送"
          className="brand-gradient flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white shadow-seal"
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
