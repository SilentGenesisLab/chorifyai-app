import { cn } from "@/lib/utils";

/**
 * 分区水墨背景垫层：把 背景3 整画置于分区最底层，叠一层宣纸薄纱保证文字可读，
 * 内容（flex）以 relative z-10 浮于其上。
 * posY 控制展示画面的哪一段（让整页背景自上而下连续过渡）。
 */
export function SectionInk({
  posY = "center",
  veil = 52,
  className,
}: {
  posY?: string;
  veil?: number;
  className?: string;
}) {
  return (
    <div
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
      aria-hidden
    >
      <img
        src="/assets/ink/hero-bg-sm.webp"
        alt=""
        loading="lazy"
        className="h-full w-full object-cover"
        style={{ objectPosition: `center ${posY}` }}
      />
      <div
        className="absolute inset-0"
        style={{
          background: `color-mix(in srgb, var(--color-paper) ${veil}%, transparent)`,
        }}
      />
    </div>
  );
}
