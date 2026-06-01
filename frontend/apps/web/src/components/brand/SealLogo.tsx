import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

/** 品牌印章标识 —— 真实 logo 图片（public/logo.png）。 */
export function SealMark({
  size = 40,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/logo.png"
      alt="Chorify"
      width={size}
      height={size}
      className={cn("shrink-0 object-contain", className)}
    />
  );
}

/**
 * 品牌组合：印章 + Chorify 字标 + 标语。
 * variant="full" 显示标语，"compact" 仅字标。
 */
export function BrandLockup({
  size = 40,
  variant = "full",
  className,
  invert = false,
}: {
  size?: number;
  variant?: "full" | "compact";
  className?: string;
  invert?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <SealMark size={size} />
      <div className="leading-none">
        <span
          className={cn(
            "font-display text-[1.45rem] font-bold tracking-tight",
            invert ? "text-white" : "text-ink",
          )}
        >
          {BRAND.name}
        </span>
        {variant === "full" && (
          <span
            className={cn(
              "mt-1 block text-[11px] tracking-[0.18em]",
              invert ? "text-white/70" : "text-muted-foreground",
            )}
          >
            {BRAND.tagline}
          </span>
        )}
      </div>
    </div>
  );
}
