import type { Metadata } from "next";
import "./globals.css";
import { BRAND } from "@/lib/brand";

export const metadata: Metadata = {
  title: `${BRAND.name} · AI 智创内容营销平台`,
  description:
    "Chorify 智创内容 · 驱动增长 — 新一代 AI 内容创作与营销平台：AI 脚本创作、智能视频生成、全域营销分发、数据洞察优化，让视频营销从此更简单。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // 字体走系统 CJK 字体栈（见 globals.css）：思源/Source Han 若已安装则优先，
  // 否则回退到 Songti/PingFang/微软雅黑等。不引外部 Google Fonts，避免国内加载阻塞。
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
