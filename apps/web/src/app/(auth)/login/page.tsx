import { Suspense } from "react";
import { Logo } from "@/components/brand/Logo";
import { LoginForm } from "@/components/login/LoginForm";
import { BRAND } from "@/lib/brand";

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      {/* soft brand backdrop */}
      <div className="pointer-events-none absolute inset-0 -z-10 bg-background" />
      <div className="pointer-events-none absolute -left-24 -top-24 -z-10 h-96 w-96 rounded-full bg-brand/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-24 -z-10 h-96 w-96 rounded-full bg-brand-pink/20 blur-3xl" />

      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-8 shadow-xl shadow-black/5">
        <Logo />
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">
          登录 {BRAND.name}
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          {BRAND.tagline}，从 {BRAND.name} 开始
        </p>

        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
