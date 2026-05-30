import { cn } from "@/lib/utils";

/* ============================================================
   水墨装饰元素 — 纯 SVG，token 取色，pointer-events-none。
   用于 Hero 与各分区的国风氛围铺陈；可被真实扣图资产替换。
   ============================================================ */

/** 远近层叠山峦 + 薄雾。side 控制朝向，可镜像。 */
export function MistMountains({
  className,
  side = "left",
}: {
  className?: string;
  side?: "left" | "right";
}) {
  return (
    <svg
      viewBox="0 0 420 320"
      fill="none"
      aria-hidden
      preserveAspectRatio="xMidYMax meet"
      className={cn(
        "pointer-events-none select-none",
        side === "right" && "-scale-x-100",
        className,
      )}
    >
      <defs>
        <linearGradient id="mtn-far" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9a9082" stopOpacity="0.45" />
          <stop offset="1" stopColor="#9a9082" stopOpacity="0.05" />
        </linearGradient>
        <linearGradient id="mtn-near" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4f4a42" stopOpacity="0.62" />
          <stop offset="0.7" stopColor="#5b554c" stopOpacity="0.28" />
          <stop offset="1" stopColor="#5b554c" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* 远山 */}
      <path
        d="M0 180 C60 120 96 132 140 150 C180 166 210 120 250 96 C300 66 350 110 420 92 L420 320 L0 320 Z"
        fill="url(#mtn-far)"
      />
      {/* 近峰 */}
      <path
        d="M0 250 C40 200 70 168 104 150 C120 142 132 150 142 168 C160 200 180 214 210 226 C260 246 300 230 360 250 C390 260 408 256 420 250 L420 320 L0 320 Z"
        fill="url(#mtn-near)"
      />
      {/* 山顶小松/亭点缀 */}
      <g stroke="#3a352e" strokeWidth="2.4" strokeLinecap="round" opacity="0.55">
        <path d="M104 150 L104 132" />
        <path d="M104 138 l-9 8 M104 138 l9 8 M104 146 l-7 7 M104 146 l7 7" />
      </g>
    </svg>
  );
}

/** 竹枝 — 2~3 竿带叶。 */
export function Bamboo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 140 360"
      fill="none"
      aria-hidden
      preserveAspectRatio="xMidYMax meet"
      className={cn("pointer-events-none select-none", className)}
    >
      <g stroke="#5d6b54" strokeWidth="5" strokeLinecap="round" opacity="0.7">
        <path d="M44 360 C40 260 46 170 42 70" />
        <path d="M86 360 C92 280 84 190 90 96" />
      </g>
      {/* 竹节 */}
      <g stroke="#48543f" strokeWidth="2" opacity="0.6">
        <path d="M37 300 h12 M39 240 h12 M41 180 h12 M40 120 h12" />
        <path d="M83 300 h12 M85 240 h12 M87 180 h12 M88 130 h12" />
      </g>
      {/* 竹叶 */}
      <g fill="#5d6b54" opacity="0.62">
        <path d="M42 96 q26 -10 44 -2 q-22 12 -44 2 Z" />
        <path d="M42 110 q-26 -6 -42 4 q24 10 42 -4 Z" />
        <path d="M90 120 q26 -8 44 0 q-22 12 -44 0 Z" />
        <path d="M90 70 q22 -14 40 -10 q-18 16 -40 10 Z" />
      </g>
    </svg>
  );
}

/** 云纹 — 金线如意卷云。 */
export function Clouds({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 160 44"
      fill="none"
      aria-hidden
      className={cn("pointer-events-none select-none", className)}
    >
      <g
        stroke="var(--color-gold)"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
        opacity="0.85"
      >
        <path d="M6 30 q10 -2 14 -10 q4 -10 16 -8 q10 2 10 12 q8 -6 16 -2" />
        <path d="M28 30 a5 5 0 1 1 8 0" />
        <path d="M86 24 q10 -2 14 -10 q4 -10 16 -8 q10 2 10 12 q8 -6 16 -2" />
        <path d="M108 24 a5 5 0 1 1 8 0" />
      </g>
    </svg>
  );
}

/** 飞鸟 — 一行点墨。 */
export function Birds({ className }: { className?: string }) {
  const b = [
    [8, 22, 1],
    [34, 12, 0.8],
    [60, 26, 1.1],
    [92, 8, 0.7],
    [120, 20, 0.9],
  ] as const;
  return (
    <svg
      viewBox="0 0 150 40"
      fill="none"
      aria-hidden
      className={cn("pointer-events-none select-none", className)}
    >
      <g stroke="#3a352e" strokeWidth="2" strokeLinecap="round" opacity="0.5">
        {b.map(([x, y, s], i) => (
          <path
            key={i}
            d={`M${x} ${y} q${6 * s} ${-5 * s} ${11 * s} 0 q${5 * s} ${-5 * s} ${11 * s} 0`}
          />
        ))}
      </g>
    </svg>
  );
}

/** 小舟 — 江上一叶。 */
export function Boat({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 120 60"
      fill="none"
      aria-hidden
      className={cn("pointer-events-none select-none", className)}
    >
      <g opacity="0.62">
        <path
          d="M18 38 q42 16 84 0 q-10 12 -42 12 q-32 0 -42 -12 Z"
          fill="#4f4a42"
        />
        <path d="M56 38 L56 16" stroke="#4f4a42" strokeWidth="2" />
        <path d="M56 18 q14 4 18 12 l-18 2 Z" fill="#7a7367" />
        <circle cx="46" cy="34" r="3" fill="#3a352e" />
      </g>
      <path d="M0 52 q60 -8 120 0" stroke="#b9ad99" strokeWidth="1.4" opacity="0.6" fill="none" />
    </svg>
  );
}

/** 竖排印章 — 红框 + 竖排字 + 底部小钤印。 */
export function VerticalSeal({
  label = "山河为伴",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "pointer-events-none inline-flex flex-col items-center gap-2 rounded-md border border-brand/35 px-2 py-3",
        className,
      )}
      aria-hidden
    >
      <span className="font-display text-lg leading-[1.5] tracking-wide text-brand/80 [writing-mode:vertical-rl]">
        {label}
      </span>
      <span className="flex h-6 w-6 items-center justify-center rounded-[4px] bg-brand text-[11px] font-bold text-white">
        印
      </span>
    </div>
  );
}

/** 分区标题前的小钤印徽标。 */
export function SealBadge({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex h-5 w-5 items-center justify-center rounded-[5px] bg-brand text-[11px] font-bold text-white shadow-seal",
        className,
      )}
    >
      C
    </span>
  );
}

/** 居中分区标题：小钤印 + 宋体大标题 + 副标题。 */
export function SectionHeading({
  title,
  subtitle,
  className,
}: {
  title: string;
  subtitle?: string;
  className?: string;
}) {
  return (
    <div className={cn("text-center", className)}>
      <h2 className="flex items-center justify-center gap-2.5 font-display text-3xl font-bold text-ink">
        <SealBadge />
        {title}
      </h2>
      {subtitle && (
        <p className="mt-3 text-sm text-muted-foreground">{subtitle}</p>
      )}
    </div>
  );
}
