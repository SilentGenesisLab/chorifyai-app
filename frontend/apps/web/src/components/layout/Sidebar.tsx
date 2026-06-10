"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Home,
  Lightbulb,
  Sparkles,
  Layers,
  Send,
  Cloud,
  Smartphone,
  Scissors,
  Languages,
  LayoutGrid,
  Music,
  Split,
  Bell,
  ChevronDown,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { NAV } from "@/lib/nav";
import { Logo } from "@/components/brand/Logo";
import { LocalStoragePanel } from "@/components/layout/LocalStoragePanel";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  home: Home,
  lightbulb: Lightbulb,
  sparkles: Sparkles,
  layers: Layers,
  send: Send,
  cloud: Cloud,
  smartphone: Smartphone,
  scissors: Scissors,
  languages: Languages,
  grid: LayoutGrid,
  music: Music,
  split: Split,
};

export function Sidebar({
  user,
  org,
}: {
  user: { nickname: string; avatarUrl: string | null };
  org: { name: string };
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/"); // 退出后回到主页（而非登录页）
    router.refresh();
  }

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="px-4 py-4">
        <Logo />
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {NAV.map((group, gi) => (
          <div key={gi}>
            {group.title && (
              <p className="mb-1 px-2.5 text-xs font-medium text-muted">
                {group.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = ICONS[item.icon] ?? Home;
                const active = isActive(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                        active
                          ? "bg-surface-muted font-medium text-foreground"
                          : "text-muted-foreground hover:bg-surface-muted hover:text-foreground",
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-[18px] w-[18px] shrink-0",
                          active ? "text-brand" : "text-muted",
                        )}
                      />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="space-y-2 border-t border-border p-3">
        <LocalStoragePanel />

        <button
          type="button"
          className="brand-gradient flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:opacity-90"
        >
          <Sparkles className="h-4 w-4" />
          生机 Agent
        </button>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex flex-1 items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-surface-muted"
          >
            <Bell className="h-[18px] w-[18px] text-muted" />
            消息通知
            <span className="ml-auto rounded-full bg-surface-muted px-1.5 text-xs text-muted">
              0
            </span>
          </button>
          <ThemeToggle up />
        </div>

        <div className="relative">
          {menuOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
              <button
                type="button"
                onClick={logout}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-foreground transition-colors hover:bg-surface-muted"
              >
                <LogOut className="h-4 w-4 text-muted" />
                退出登录
              </button>
            </div>
          )}
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-surface-muted"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-muted text-sm font-medium text-foreground">
              {user.nickname.charAt(0)}
            </span>
            <span className="min-w-0 flex-1 text-left">
              <span className="block truncate text-sm font-medium text-foreground">
                {user.nickname}
              </span>
              <span className="block truncate text-xs text-muted">
                {org.name}
              </span>
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-muted transition-transform",
                menuOpen && "rotate-180",
              )}
            />
          </button>
        </div>
      </div>
    </aside>
  );
}
