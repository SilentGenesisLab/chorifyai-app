import { getSession } from "@/lib/auth/session";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";

export default async function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();
  return (
    <div className="min-h-screen bg-background">
      <MarketingNav authed={!!session} />
      {children}
      <MarketingFooter />
    </div>
  );
}
