import { CAPABILITIES } from "@/lib/marketing";
import { SectionHeading } from "@/components/decor/ink";
import { IconChip, type Tone } from "./shared";

const TONES: Tone[] = ["brand", "jade", "gold", "azure", "violet", "brand"];

export function CoreCapabilities() {
  return (
    <section id="capabilities" className="relative overflow-hidden bg-surface-muted/50 py-20">
      <img
        src="/assets/ink/mountains.webp"
        alt=""
        aria-hidden
        className="pointer-events-none absolute -left-10 bottom-0 h-64 opacity-25 mix-blend-multiply"
      />
      <img
        src="/assets/ink/bamboo.webp"
        alt=""
        aria-hidden
        className="pointer-events-none absolute -right-4 top-8 h-72 opacity-30 mix-blend-multiply"
      />
      <div className="relative z-10 mx-auto max-w-7xl px-6">
        <SectionHeading title={CAPABILITIES.title} />

        <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.items.map((it, i) => (
            <div
              key={it.title}
              className="ink-card flex items-start gap-4 p-6 transition hover:-translate-y-0.5 hover:shadow-lg"
            >
              <IconChip icon={it.icon} tone={TONES[i % TONES.length]} size={50} />
              <div>
                <h3 className="font-display text-lg font-bold text-ink">{it.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {it.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
