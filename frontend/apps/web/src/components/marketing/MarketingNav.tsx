import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { BrandLockup } from "@/components/brand/SealLogo";
import { LoginButton } from "@/components/auth/LoginModal";
import { NAV_LINKS } from "@/lib/marketing";

export function MarketingNav({ authed = false }: { authed?: boolean }) {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-paper/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" aria-label="Chorify 首页">
          <BrandLockup size={34} />
        </Link>

        <nav className="hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) =>
            link.children ? (
              <div key={link.label} className="group relative">
                <button
                  type="button"
                  className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-ink"
                >
                  {link.label}
                  <ChevronDown className="h-3.5 w-3.5 transition-transform group-hover:rotate-180" />
                </button>
                <div className="absolute left-0 top-full hidden pt-2 group-hover:block">
                  <div className="ink-card w-44 p-1.5">
                    {link.children.map((c) => (
                      <Link
                        key={c.label}
                        href={c.href}
                        className="block rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-surface-muted hover:text-ink"
                      >
                        {c.label}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <Link
                key={link.label}
                href={link.href}
                className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-ink"
              >
                {link.label}
              </Link>
            ),
          )}
        </nav>

        <div className="flex items-center gap-2.5">
          {authed ? (
            <Link
              href="/workspace"
              className="brand-gradient inline-flex h-9 items-center rounded-lg px-4 text-sm font-medium text-white shadow-seal transition hover:opacity-95"
            >
              进入工作台
            </Link>
          ) : (
            <>
              <LoginButton className="hidden h-9 items-center rounded-lg border border-border-strong px-4 text-sm font-medium text-ink transition-colors hover:bg-surface-muted sm:inline-flex">
                登录
              </LoginButton>
              <LoginButton className="brand-gradient inline-flex h-9 items-center rounded-lg px-4 text-sm font-medium text-white shadow-seal transition hover:opacity-95">
                开始使用
              </LoginButton>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
