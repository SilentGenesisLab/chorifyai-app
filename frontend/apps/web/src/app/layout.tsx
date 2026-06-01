import type { Metadata } from "next";
import "./globals.css";
import { BRAND } from "@/lib/brand";

export const metadata: Metadata = {
  title: `${BRAND.name} · AI 智创内容营销平台`,
  description:
    "Chorify 智创内容 · 驱动增长 — 新一代 AI 内容创作与营销平台：AI 脚本创作、智能视频生成、全域营销分发、数据洞察优化，让视频营销从此更简单。",
};

// 在首帧绘制前设定主题，避免深浅色闪烁（FOUC）。默认 "system" = 跟随系统。
const themeScript = `
(function(){try{
  var t = localStorage.getItem('theme') || 'system';
  var dark = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  if (dark) document.documentElement.classList.add('dark');
}catch(e){}})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // 字体走系统 CJK 字体栈（见 globals.css）；主题由上面脚本在水合前设定。
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
