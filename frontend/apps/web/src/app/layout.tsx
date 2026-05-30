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
  return (
    <html lang="zh-CN">
      <head>
        {/* 思源宋体/黑体作为渐进增强；系统 CJK 字体兜底（见 globals.css 字体栈）*/}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@500;700;900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
