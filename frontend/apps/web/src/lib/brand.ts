/** Single source of truth for product branding. Change here to re-brand. */
export const BRAND = {
  name: process.env.NEXT_PUBLIC_APP_NAME ?? "Chorify",
  version: "5.5",
  /** 主标语（落地页/页脚/登录页通用） */
  tagline: "智创内容 · 驱动增长",
  /** 一句话价值主张 */
  slogan: "AI 智创，视频营销从此更简单",
} as const;
