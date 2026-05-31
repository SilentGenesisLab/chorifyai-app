import { getSession } from "@/lib/auth/session";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";
import { LoginModalProvider } from "@/components/auth/LoginModal";

export default async function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();
  return (
    <LoginModalProvider>
      <div className="min-h-screen bg-background">
        <MarketingNav authed={!!session} />
        {children}
        <MarketingFooter />
      </div>
    </LoginModalProvider>
  );
}
