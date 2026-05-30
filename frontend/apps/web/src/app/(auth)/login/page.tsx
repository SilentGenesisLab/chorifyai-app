import { Suspense } from "react";
import Link from "next/link";
import { BrandLockup } from "@/components/brand/SealLogo";
import { MistMountains, Birds } from "@/components/decor/ink";
import { LoginForm } from "@/components/login/LoginForm";
import { BRAND } from "@/lib/brand";

export default function LoginPage() {
  return (
    <main className="paper-wash relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      {/* 水墨背景 */}
      <div className="pointer-events-none absolute inset-0 -z-10 paper-grid opacity-70" />
      <div className="pointer-events-none absolute -left-10 -top-6 -z-10 h-72 w-[40%] max-w-md">
        <MistMountains side="left" className="h-full w-full opacity-70" />
      </div>
      <MistMountains
        side="right"
        className="pointer-events-none absolute -right-10 bottom-0 -z-10 h-80 w-[44%] max-w-lg opacity-60"
      />
      <Birds className="pointer-events-none absolute left-[20%] top-16 -z-10 w-32" />
      <div className="pointer-events-none absolute right-[10%] top-1/3 -z-10 h-72 w-72 rounded-full bg-brand/10 blur-3xl" />

      <div className="ink-card w-full max-w-md p-8 shadow-xl shadow-black/5">
        <Link href="/" aria-label="返回首页">
          <BrandLockup />
        </Link>
        <h1 className="mt-7 font-display text-2xl font-bold tracking-tight">
          登录 {BRAND.name}
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {BRAND.slogan}
        </p>

        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
