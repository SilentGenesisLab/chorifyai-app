import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

/**
 * 朱红印章风 "C" 标识 — 纯 SVG，无需外部图片资源。
 * 红底圆角方印 + 镂空弧形 C + 轻微做旧纹理。
 */
export function SealMark({
  size = 40,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      className={cn("shrink-0", className)}
      aria-hidden
    >
      <defs>
        {/* 做旧/斑驳纹理 */}
        <filter id="seal-distress">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves="2"
            seed="7"
            result="n"
          />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.1 1.05" />
          <feComposite in="SourceGraphic" operator="in" />
        </filter>
        <clipPath id="seal-clip">
          <rect x="6" y="6" width="88" height="88" rx="18" />
        </clipPath>
      </defs>

      {/* 印底 */}
      <rect x="6" y="6" width="88" height="88" rx="18" fill="var(--color-brand)" />
      {/* 内描边（碑刻感）*/}
      <rect
        x="13"
        y="13"
        width="74"
        height="74"
        rx="13"
        fill="none"
        stroke="rgba(255,255,255,0.28)"
        strokeWidth="2"
      />
      {/* 镂空弧形 C */}
      <path
        d="M70 33
           A26 26 0 1 0 70 67"
        fill="none"
        stroke="#fdfbf6"
        strokeWidth="13"
        strokeLinecap="butt"
      />
      {/* 篆刻收笔小点 */}
      <circle cx="70" cy="33" r="6.5" fill="#fdfbf6" />
      <circle cx="70" cy="67" r="6.5" fill="#fdfbf6" />

      {/* 斑驳叠加 */}
      <g clipPath="url(#seal-clip)" opacity="0.12">
        <rect x="6" y="6" width="88" height="88" fill="#fdfbf6" filter="url(#seal-distress)" />
      </g>
    </svg>
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
