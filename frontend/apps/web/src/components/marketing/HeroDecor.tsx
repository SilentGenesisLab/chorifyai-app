/** Hero 区背景：真实水墨画 (背景3) + 提亮/过渡叠层 + 右缘书法钤印。
 *  渐变用 inline style（Tailwind v4 无法对 arbitrary var() 套 /opacity，会生成非法 CSS）。 */
export function HeroDecor() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {/* 水墨画背景 */}
      <img
        src="/assets/ink/hero-bg.webp"
        alt=""
        className="absolute inset-0 h-full w-full object-cover object-top opacity-95"
      />
      {/* 左侧提亮（保证标题可读） */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(to right, color-mix(in srgb, var(--color-paper) 85%, transparent) 0%, color-mix(in srgb, var(--color-paper) 32%, transparent) 46%, transparent 80%)",
        }}
      />
      {/* 顶部轻纱 */}
      <div
        className="absolute inset-x-0 top-0 h-24"
        style={{
          background:
            "linear-gradient(to bottom, color-mix(in srgb, var(--color-paper) 70%, transparent), transparent)",
        }}
      />
      {/* 底部过渡到下一区 */}
      <div
        className="absolute inset-x-0 bottom-0 h-44"
        style={{
          background: "linear-gradient(to bottom, transparent, var(--color-background))",
        }}
      />
      {/* 右缘竖排书法钤印 */}
      <img
        src="/assets/ink/calligraphy.webp"
        alt=""
        className="absolute right-3 top-[22%] hidden h-64 opacity-85 mix-blend-multiply xl:block"
      />
    </div>
  );
}
