import Link from "next/link";
import { ArrowRight, Play } from "lucide-react";
import { HERO } from "@/lib/marketing";
import { SealBadge } from "@/components/decor/ink";
import { LoginButton } from "@/components/auth/LoginModal";
import { AssistantPanel } from "./AssistantPanel";

export function Hero() {
  return (
    <div className="relative z-10 grid items-center gap-10 pt-14 pb-12 lg:grid-cols-[1.05fr_0.95fr] lg:pt-20 lg:pb-16">
      {/* 左：文案 */}
      <div>
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3.5 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur">
          <SealBadge className="h-4 w-4 text-[9px]" />
          {HERO.badge}
        </span>

        <h1 className="mt-6 font-display text-5xl font-bold leading-[1.18] text-ink sm:text-6xl">
          {HERO.titleTop}
          <br />
          <span className="relative">
            {HERO.titleBottom}
            <span className="ml-2 inline-flex h-7 w-7 -translate-y-2 items-center justify-center rounded-[6px] bg-brand align-top text-xs font-bold text-white shadow-seal">
              印
            </span>
          </span>
        </h1>

        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground">
          {HERO.subtitle}
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-4">
          <LoginButton className="brand-gradient inline-flex h-12 items-center gap-2 rounded-xl px-7 text-base font-medium text-white shadow-seal transition hover:opacity-95">
            {HERO.primaryCta}
            <ArrowRight className="h-4 w-4" />
          </LoginButton>
          <Link
            href="#footer"
            className="inline-flex h-12 items-center gap-2 rounded-xl border border-border-strong bg-surface/70 px-6 text-base font-medium text-ink backdrop-blur transition-colors hover:bg-surface-muted"
          >
            <Play className="h-4 w-4 fill-current" />
            {HERO.secondaryCta}
          </Link>
        </div>
      </div>

      {/* 右：智能助理 */}
      <div className="flex justify-center lg:justify-end">
        <AssistantPanel />
      </div>
    </div>
  );
}
