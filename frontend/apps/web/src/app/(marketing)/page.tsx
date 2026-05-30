import { Hero } from "@/components/marketing/Hero";
import { HeroDecor } from "@/components/marketing/HeroDecor";
import { FeatureCards } from "@/components/marketing/FeatureCards";
import { StatsBar } from "@/components/marketing/StatsBar";
import { ProcessFlow } from "@/components/marketing/ProcessFlow";
import { CoreCapabilities } from "@/components/marketing/CoreCapabilities";
import { IndustrySolutions } from "@/components/marketing/IndustrySolutions";
import { CustomerCases } from "@/components/marketing/CustomerCases";
import { TemplateCenter } from "@/components/marketing/TemplateCenter";
import { Faq } from "@/components/marketing/Faq";
import { FloatingToolbar } from "@/components/marketing/FloatingToolbar";
import { SectionInk } from "@/components/marketing/SectionInk";

export default function LandingPage() {
  return (
    <>
      <FloatingToolbar />

      {/* 首屏 · 宣纸水墨 band */}
      <section className="paper-wash relative overflow-hidden">
        <HeroDecor />
        <div className="mx-auto max-w-7xl px-6">
          <Hero />
          <FeatureCards />
          <StatsBar />
          <div className="h-12" />
        </div>
      </section>

      {/* 从洞察到增长 */}
      <ProcessFlow />

      {/* 核心能力 */}
      <CoreCapabilities />

      {/* 行业解决方案（左·宽） + 客户案例（右） */}
      <section className="relative overflow-hidden py-20">
        <SectionInk posY="60%" />
        <div className="relative z-10 mx-auto grid max-w-7xl items-start gap-12 px-6 lg:grid-cols-[1.15fr_0.85fr]">
          <IndustrySolutions />
          <CustomerCases />
        </div>
      </section>

      {/* 模板中心 */}
      <TemplateCenter />

      {/* 常见问题 */}
      <Faq />
    </>
  );
}
