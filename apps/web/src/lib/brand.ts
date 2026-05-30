/** Single source of truth for product branding. Change here to re-brand. */
export const BRAND = {
  name: process.env.NEXT_PUBLIC_APP_NAME ?? "Chorify",
  version: "5.5",
  tagline: "轻松开启工作",
} as const;
