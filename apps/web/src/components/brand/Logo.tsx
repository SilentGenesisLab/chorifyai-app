import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

export function Logo({
  className,
  showVersion = true,
}: {
  className?: string;
  showVersion?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="brand-gradient flex h-8 w-8 items-center justify-center rounded-lg text-base font-bold text-white shadow-sm">
        {BRAND.name.charAt(0)}
      </div>
      <span className="text-xl font-semibold tracking-tight">{BRAND.name}</span>
      {showVersion && (
        <span className="brand-gradient rounded px-1.5 py-0.5 text-[10px] font-semibold text-white">
          {BRAND.version}
        </span>
      )}
    </div>
  );
}
