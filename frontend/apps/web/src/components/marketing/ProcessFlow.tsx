import { Fragment } from "react";
import { ArrowRight } from "lucide-react";
import { PROCESS } from "@/lib/marketing";
import { SectionHeading } from "@/components/decor/ink";
import { SectionInk } from "./SectionInk";
import { IconChip, type Tone } from "./shared";

const TONES: Tone[] = ["brand", "gold", "jade", "azure", "violet"];

export function ProcessFlow() {
  return (
    <section className="relative overflow-hidden py-20">
      <SectionInk posY="24%" />
      <div className="relative z-10 mx-auto max-w-7xl px-6">
        <SectionHeading title={PROCESS.title} subtitle={PROCESS.subtitle} />

        <div className="mt-14 flex flex-col items-center gap-6 lg:flex-row lg:items-start lg:justify-center lg:gap-2">
          {PROCESS.steps.map((step, i) => (
            <Fragment key={step.title}>
              <div className="flex flex-col items-center text-center lg:w-44">
                <div className="rounded-full bg-surface p-2 shadow-sm ring-1 ring-border">
                  <IconChip icon={step.icon} tone={TONES[i % TONES.length]} size={54} />
                </div>
                <h3 className="mt-4 font-display text-lg font-bold text-ink">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {step.desc}
                </p>
              </div>

              {i < PROCESS.steps.length - 1 && (
                <ArrowRight className="h-5 w-5 shrink-0 rotate-90 text-border-strong lg:mt-10 lg:rotate-0" />
              )}
            </Fragment>
          ))}
        </div>
      </div>
    </section>
  );
}
