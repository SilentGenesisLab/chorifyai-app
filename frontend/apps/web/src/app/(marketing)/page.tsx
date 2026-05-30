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

      {/* 行业解决方案 + 客户案例 */}
      <section className="mx-auto grid max-w-7xl gap-12 px-6 py-20 lg:grid-cols-2">
        <IndustrySolutions />
        <CustomerCases />
      </section>

      {/* 模板中心 */}
      <TemplateCenter />

      {/* 常见问题 */}
      <Faq />
    </>
  );
}
