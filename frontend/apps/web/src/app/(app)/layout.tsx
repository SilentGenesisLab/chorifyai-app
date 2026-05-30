import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth/current-user";
import { Sidebar } from "@/components/layout/Sidebar";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const ctx = await getCurrentUser();
  if (!ctx) redirect("/login");

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar
        user={{
          nickname: ctx.user.nickname ?? "用户",
          avatarUrl: ctx.user.avatarUrl ?? null,
        }}
        org={{ name: ctx.currentOrg?.name ?? "" }}
      />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
