/**
 * 落地页内容（图4 复刻）。集中管理文案，组件只负责渲染。
 * icon 字段为字符串 key，在组件内映射到 lucide 图标。
 */

export type NavLink = { label: string; href: string; children?: { label: string; href: string }[] };

export const NAV_LINKS: NavLink[] = [
  {
    label: "产品",
    href: "#capabilities",
    children: [
      { label: "AI 脚本创作", href: "#capabilities" },
      { label: "智能视频生成", href: "#capabilities" },
      { label: "全域营销分发", href: "#capabilities" },
      { label: "数据洞察优化", href: "#capabilities" },
    ],
  },
  {
    label: "解决方案",
    href: "#solutions",
    children: [
      { label: "美妆电商", href: "#solutions" },
      { label: "新消费品牌", href: "#solutions" },
      { label: "企业营销团队", href: "#solutions" },
    ],
  },
  { label: "模板中心", href: "#templates" },
  { label: "价格", href: "#pricing" },
  {
    label: "资源",
    href: "#faq",
    children: [
      { label: "帮助文档", href: "#faq" },
      { label: "教程视频", href: "#faq" },
      { label: "行业资讯", href: "#faq" },
    ],
  },
  { label: "关于我们", href: "#footer" },
];

export const HERO = {
  badge: "新一代 AI 内容创作与营销平台",
  titleTop: "Chorify 让视频营销",
  titleBottom: "从此更简单",
  subtitle:
    "让 AI 成为你的创意伙伴，内容生产、营销分发、数据洞察一体化，助力企业高效打造爆款视频，实现生意增长。",
  primaryCta: "开始免费体验",
  secondaryCta: "预约产品演示",
};

export const STATS = [
  { value: "10万+", label: "企业用户的共同选择" },
  { value: "50亿+", label: "视频生成与分发" },
  { value: "99.9%", label: "企业级稳定性保障" },
];

/** Hero 智能助理面板 */
export const ASSISTANT = {
  title: "Chorify 智能助理",
  tag: "/brief",
  greeting: "上午好，创作者 👋",
  intro: "告诉我你的目标，我来帮你搞定后续的内容创作与营销。",
  actions: [
    { icon: "fileText", title: "生成爆款视频脚本", desc: "基于热点与行业模板，一键生成高转化脚本", tone: "jade" },
    { icon: "clapper", title: "制作短视频", desc: "智能匹配素材、配音，快速成片", tone: "azure" },
    { icon: "barChart", title: "分析投放数据", desc: "多维度洞察内容表现，优化内容策略", tone: "brand" },
  ],
  placeholder: "输入你的需求，如：为国风美妆产品生成宣传视频脚本",
};

/** Hero 下方四张能力卡 */
export const FEATURE_CARDS = [
  { icon: "brush", tone: "brand", title: "AI 脚本创作", desc: "深度理解行业与卖点，10 倍效率产出优质脚本。" },
  { icon: "clapper", tone: "jade", title: "智能视频生成", desc: "素材秒配、智能剪辑，一键生成高质量视频。" },
  { icon: "globe", tone: "azure", title: "全域营销分发", desc: "一站式分发主流平台，提升曝光与转化效率。" },
  { icon: "barChart", tone: "gold", title: "数据洞察优化", desc: "可视化数据看板，驱动更科学的内容决策。" },
];

/** 从洞察到增长 — 五步 */
export const PROCESS = {
  title: "从洞察到增长",
  subtitle: "五步闭环，高效打造爆款内容，驱动持续增长",
  steps: [
    { icon: "compass", title: "策略洞察", desc: "洞察行业趋势与用户需求，明确内容方向" },
    { icon: "penTool", title: "脚本生成", desc: "AI 生成爆款脚本，优化文案与结构" },
    { icon: "fileText", title: "画面建议", desc: "智能匹配转场与画面，提供创意灵感" },
    { icon: "play", title: "视频制作", desc: "自动剪辑、配音配乐，一键生成视频" },
    { icon: "trendingUp", title: "分发复盘", desc: "多平台分发与数据复盘，持续优化迭代" },
  ],
};

/** 核心能力 — 六项 */
export const CAPABILITIES = {
  title: "核心能力",
  items: [
    { icon: "fileSignature", title: "AI Brief 生成", desc: "智能理解需求，自动生成精准的内容 Brief" },
    { icon: "feather", title: "脚本智能创作", desc: "多模型加持，生成要素齐备、有吸引力的爆款脚本" },
    { icon: "folderTree", title: "素材资产管理", desc: "统一管理素材与品牌资产，高效复用" },
    { icon: "send", title: "多平台一键发布", desc: "支持主流平台分发，节省运营时间" },
    { icon: "barChart", title: "数据分析洞察", desc: "多维度数据看板，洞察内容表现驱动科学决策" },
    { icon: "users", title: "团队协作管理", desc: "多人协作与权限管理，提升团队效率" },
  ],
};

/** 行业解决方案 — 三类 */
export const SOLUTIONS = {
  title: "行业解决方案",
  items: [
    { tone: "brand", tag: "美妆电商", title: "美妆电商", desc: "从种草到转化，一体化内容策略，提升带货转化" },
    { tone: "jade", tag: "新消费", title: "新消费品牌", desc: "打造品牌声量，沉淀内容资产，驱动品牌长效增长" },
    { tone: "azure", tag: "企业", title: "企业营销团队", desc: "统一内容生产与协作流程，提升团队效能" },
  ],
};

/** 客户案例 */
export const CASES = {
  title: "客户案例",
  metrics: [
    { value: "120%+", label: "平均播放增长" },
    { value: "65%+", label: "转化率提升" },
    { value: "80%+", label: "内容生产效率提升" },
  ],
  brands: ["完美日记", "三只松鼠", "元气森林", "花西子", "Ubras", "认养一头牛", "良品铺子", "蕉内"],
  testimonial: {
    quote:
      "Chorify 帮助我们实现了内容生产效率的飞跃，从脚本到分发一站式搞定，ROI 提升了 120%。",
    author: "完美日记 · 数字营销负责人",
  },
};

/** 模板中心 */
export const TEMPLATES = {
  title: "模板中心",
  tabs: ["热门模板", "电商带货", "品牌宣传", "产品种草", "节日活动", "知识科普"],
  cards: [
    { badge: "热门", title: "新品上桩热销", desc: "快速打造新品爆光视频", tone: "brand" },
    { badge: "提升", title: "产品种草测评", desc: "真实体验，提升转化率", tone: "jade" },
    { badge: "热门", title: "节日营销活动", desc: "紧扣节日，激发购买", tone: "gold" },
    { badge: "提升", title: "品牌故事宣传", desc: "传递品牌温度与理念", tone: "azure" },
    { badge: "热门", title: "用户评价合集", desc: "真实口碑，增强信任感", tone: "violet" },
  ],
};

/** 常见问题 */
export const FAQ = {
  title: "常见问题",
  items: [
    {
      q: "Chorify 适合哪些行业使用？",
      a: "美妆、电商、本地生活、新消费品牌、3C、教育等需要规模化生产营销视频的行业均适用，平台内置多行业模板与最佳实践。",
    },
    {
      q: "使用 Chorify 需要具备视频制作经验吗？",
      a: "无需任何剪辑经验。从脚本、素材到成片，AI 全流程辅助，会打字就能产出专业级营销视频。",
    },
    {
      q: "AI 生成的内容是否可商用？",
      a: "平台生成内容支持商业用途，并提供素材授权与合规审核能力，帮助企业放心使用。",
    },
    {
      q: "我的数据安全如何保障？",
      a: "采用企业级数据隔离与加密存储，支持私有化部署与数据导出，保障企业数据自主可控。",
    },
  ],
};

/** 页脚 */
export const FOOTER = {
  intro: "新一代 AI 内容创作与营销平台\n让内容创造价值，让增长更简单",
  columns: [
    { title: "产品", links: ["产品功能", "模板中心", "定价方案", "更新日志"] },
    { title: "解决方案", links: ["美妆电商", "新消费品牌", "企业营销团队", "更多行业"] },
    { title: "资源中心", links: ["帮助文档", "教程视频", "行业资讯", "博客资讯"] },
    { title: "公司", links: ["关于我们", "加入我们", "联系我们", "隐私政策"] },
  ],
  contact: {
    hours: "工作时间 9:00 - 18:00（周一至周五）",
    phone: "400-888-1998",
    email: "service@chorify.com",
  },
  copyright: "© 2026 Chorify. All Rights Reserved.",
  icp: "粤ICP备2023123456号-1·粤公网安备 440300020012345号",
};
