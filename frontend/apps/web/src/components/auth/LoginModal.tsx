"use client";

import {
  createContext,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { SealMark } from "@/components/brand/SealLogo";
import { LoginForm } from "@/components/login/LoginForm";
import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

type Ctx = { openLogin: () => void; closeLogin: () => void; isOpen: boolean };
const LoginCtx = createContext<Ctx>({
  openLogin: () => {},
  closeLogin: () => {},
  isOpen: false,
});

export function useLoginModal() {
  return useContext(LoginCtx);
}

/** 全站登录弹窗：在首页等任意位置以弹窗形式登录，不跳转新页面。 */
export function LoginModalProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  const openLogin = useCallback(() => setOpen(true), []);
  const closeLogin = useCallback(() => setOpen(false), []);

  // Esc 关闭 + 打开时锁定背景滚动
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <LoginCtx.Provider value={{ openLogin, closeLogin, isOpen: open }}>
      {children}

      {open && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          {/* 遮罩 */}
          <button
            type="button"
            aria-label="关闭登录"
            onClick={closeLogin}
            className="absolute inset-0 cursor-default bg-ink/45 backdrop-blur-sm"
          />
          {/* 弹窗 */}
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`登录 ${BRAND.name}`}
            className="ink-card relative z-10 w-full max-w-md p-8 shadow-xl shadow-black/10"
          >
            <button
              type="button"
              onClick={closeLogin}
              aria-label="关闭"
              className="absolute right-3.5 top-3.5 flex h-8 w-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-muted hover:text-ink"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="flex items-center gap-2.5">
              <SealMark size={36} />
              <span className="font-display text-xl font-bold tracking-tight text-ink">
                登录 {BRAND.name}
              </span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{BRAND.slogan}</p>

            <Suspense fallback={null}>
              <LoginForm
                onSuccess={() => {
                  setOpen(false);
                  // 登录成功直接进工作台（cookie 已设，受保护路由可正常进入）
                  router.replace("/workspace");
                }}
              />
            </Suspense>
          </div>
        </div>
      )}
    </LoginCtx.Provider>
  );
}

/** 触发登录弹窗的按钮（在 server 组件里也能用：它是 client）。 */
export function LoginButton({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const { openLogin } = useLoginModal();
  return (
    <button type="button" onClick={openLogin} className={cn(className)}>
      {children}
    </button>
  );
}
