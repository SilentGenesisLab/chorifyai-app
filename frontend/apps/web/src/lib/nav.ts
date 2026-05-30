// Sidebar navigation config. `icon` keys are mapped to lucide components
// in components/layout/Sidebar.tsx (keeps this file JSX-free / server-safe).
export type NavItem = { label: string; href: string; icon: string };
export type NavGroup = { title?: string; items: NavItem[] };

export const NAV: NavGroup[] = [
  {
    items: [{ label: "开始工作", href: "/workspace", icon: "home" }],
  },
  {
    title: "工作流",
    items: [
      { label: "编导灵感", href: "/inspiration", icon: "lightbulb" },
      { label: "素材生产", href: "/material", icon: "sparkles" },
      { label: "合成量产", href: "/compose", icon: "layers" },
      { label: "投放分发", href: "/distribute", icon: "send" },
    ],
  },
  {
    title: "服务",
    items: [
      { label: "云盘", href: "/drive", icon: "cloud" },
      { label: "手机协同", href: "/mobile", icon: "smartphone" },
      { label: "直播切片", href: "/live", icon: "scissors" },
      { label: "视频翻译", href: "/translate", icon: "languages" },
      { label: "矩阵宝", href: "/matrix", icon: "grid" },
      { label: "BGM市场", href: "/bgm", icon: "music" },
      { label: "视频拆分", href: "/split", icon: "split" },
    ],
  },
];

/** Flat lookup of label by path, for page titles. */
export const NAV_LABEL: Record<string, string> = Object.fromEntries(
  NAV.flatMap((g) => g.items).map((i) => [i.href, i.label]),
);
