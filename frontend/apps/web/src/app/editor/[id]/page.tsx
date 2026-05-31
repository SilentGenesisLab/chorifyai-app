import { redirect, notFound } from "next/navigation";
import { getCurrentUser } from "@/lib/auth/current-user";
import { prisma } from "@/lib/db";
import { ComposeEditor } from "@/components/compose/ComposeEditor";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const ctx = await getCurrentUser();
  if (!ctx) redirect("/login");

  const project = ctx.currentOrg
    ? await prisma.project.findFirst({
        where: { id, orgId: ctx.currentOrg.id },
      })
    : null;
  if (!project) notFound();

  return (
    <ComposeEditor
      project={{
        id: project.id,
        name: project.name,
        width: project.width,
        height: project.height,
      }}
    />
  );
}
