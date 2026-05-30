import { LayoutGrid, Pencil, Hexagon } from "lucide-react";

const ITEMS = [
  { icon: LayoutGrid, label: "应用" },
  { icon: Pencil, label: "创作" },
  { icon: Hexagon, label: "设置" },
];

export function FloatingToolbar() {
  return (
    <div className="fixed right-4 top-1/2 z-40 hidden -translate-y-1/2 flex-col gap-3 xl:flex">
      {ITEMS.map(({ icon: Icon, label }) => (
        <button
          key={label}
          type="button"
          aria-label={label}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border bg-surface/90 text-muted-foreground shadow-md backdrop-blur transition-colors hover:border-brand/30 hover:text-brand"
        >
          <Icon className="h-[18px] w-[18px]" strokeWidth={1.7} />
        </button>
      ))}
    </div>
  );
}
