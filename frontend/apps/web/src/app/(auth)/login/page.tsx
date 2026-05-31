import { Suspense } from "react";
import Link from "next/link";
import { BrandLockup } from "@/components/brand/SealLogo";
import { LoginForm } from "@/components/login/LoginForm";
import { BRAND } from "@/lib/brand";

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      {/* 水墨山水背景 */}
      <img
        src="/assets/ink/login-bg.webp"
        alt=""
        aria-hidden
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
      />
      {/* 宣纸薄纱，保证表单可读 */}
      <div className="pointer-events-none absolute inset-0 bg-[var(--color-paper)]/55" />

      <div className="ink-card relative z-10 w-full max-w-md bg-surface/90 p-8 shadow-2xl shadow-black/20 backdrop-blur-md">
        <Link href="/" aria-label="返回首页">
          <BrandLockup />
        </Link>
        <h1 className="mt-7 font-display text-2xl font-bold tracking-tight">
          登录 {BRAND.name}
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{BRAND.slogan}</p>

        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
