"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const USER_AGREEMENT_URL =
  "https://yhai.sligenai.cn/silgene-protocolsv2/protocols/slientgene/ProductUserAgreement.html";
const PRIVACY_URL =
  "https://yhai.sligenai.cn/silgene-protocolsv2/protocols/slientgene/ProductPrivacyPolicy.html";

export function LoginForm({ onSuccess }: { onSuccess?: () => void } = {}) {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/workspace";

  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const phoneValid = /^1[3-9]\d{9}$/.test(phone);

  const sendCode = useCallback(async () => {
    setError(null);
    if (!phoneValid) {
      setError("请输入正确的手机号");
      return;
    }
    if (!agreed) {
      setError("请先阅读并勾选同意《用户协议》和《隐私协议》");
      return;
    }
    setSending(true);
    try {
      const res = await fetch("/api/auth/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setError(data.error || "发送失败");
        return;
      }
      setCountdown(60);
      if (data.devCode) {
        setDevCode(data.devCode);
        setCode(data.devCode);
      }
    } catch {
      setError("网络错误，请重试");
    } finally {
      setSending(false);
    }
  }, [phone, phoneValid, agreed]);

  const submit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      setError(null);
      if (!phoneValid) {
        setError("请输入正确的手机号");
        return;
      }
      if (!/^\d{6}$/.test(code)) {
        setError("请输入 6 位验证码");
        return;
      }
      if (!agreed) {
        setError("请先阅读并勾选同意《用户协议》和《隐私协议》");
        return;
      }
      setLoading(true);
      try {
        const res = await fetch("/api/auth/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone, code }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          setError(data.error || "登录失败");
          return;
        }
        if (onSuccess) {
          onSuccess();
        } else {
          router.replace(next);
          router.refresh();
        }
      } catch {
        setError("网络错误，请重试");
      } finally {
        setLoading(false);
      }
    },
    [phone, code, phoneValid, next, router, onSuccess, agreed],
  );

  return (
    <form onSubmit={submit} className="mt-7 flex flex-col gap-3.5">
      <div>
        <label className="mb-1.5 block text-sm text-muted-foreground">手机号</label>
        <Input
          inputMode="numeric"
          autoComplete="tel"
          placeholder="请输入手机号"
          value={phone}
          maxLength={11}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
        />
      </div>

      <div>
        <label className="mb-1.5 block text-sm text-muted-foreground">验证码</label>
        <div className="flex gap-2">
          <Input
            inputMode="numeric"
            placeholder="6 位验证码"
            value={code}
            maxLength={6}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          />
          <Button
            type="button"
            variant="outline"
            className="w-32 shrink-0"
            disabled={sending || countdown > 0 || !phoneValid}
            onClick={sendCode}
          >
            {countdown > 0 ? `${countdown}s` : sending ? "发送中…" : "获取验证码"}
          </Button>
        </div>
      </div>

      {devCode && (
        <p className="rounded-lg bg-surface-muted px-3 py-2 text-xs text-muted-foreground">
          开发模式：验证码 <span className="font-semibold text-foreground">{devCode}</span>（已自动填入）
        </p>
      )}

      {error && <p className="text-sm text-brand">{error}</p>}

      <Button type="submit" size="lg" className="mt-1" disabled={loading}>
        {loading ? "登录中…" : "登录 / 注册"}
      </Button>

      <label className="mt-1 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 shrink-0 cursor-pointer accent-brand"
        />
        <span>
          我已阅读并同意
          <a
            href={USER_AGREEMENT_URL}
            target="_blank"
            rel="noreferrer"
            className="text-brand hover:underline"
          >
            《用户协议》
          </a>
          和
          <a
            href={PRIVACY_URL}
            target="_blank"
            rel="noreferrer"
            className="text-brand hover:underline"
          >
            《隐私协议》
          </a>
        </span>
      </label>

      <p className="text-center text-xs text-muted">未注册的手机号将自动创建账号</p>
    </form>
  );
}
