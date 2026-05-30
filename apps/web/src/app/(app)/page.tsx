import { getCurrentUser } from "@/lib/auth/current-user";
import { prisma } from "@/lib/db";
import { HeroTools } from "@/components/home/HeroTools";
import { RecentProjects } from "@/components/home/RecentProjects";
import { BRAND } from "@/lib/brand";

export default async function HomePage() {
  const ctx = await getCurrentUser();
  const orgId = ctx?.currentOrg?.id;

  const projects = orgId
    ? await prisma.project.findMany({
        where: { orgId },
        orderBy: { updatedAt: "desc" },
        take: 12,
      })
    : [];

  const recent = projects.map((p) => ({
    id: p.id,
    name: p.name,
    type: p.type,
    comboCount: p.comboCount,
    updatedAt: p.updatedAt.toISOString(),
  }));

  return (
    <div className="mx-auto max-w-6xl px-8 py-12">
      <h1 className="text-center text-3xl font-bold tracking-tight">
        {BRAND.tagline} 从{" "}
        <span className="brand-text-gradient">{BRAND.name}</span> 开始！
      </h1>

      <HeroTools />
      <RecentProjects projects={recent} />
    </div>
  );
}
