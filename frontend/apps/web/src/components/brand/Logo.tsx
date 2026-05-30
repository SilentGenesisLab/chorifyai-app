import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { SealMark } from "./SealLogo";

export function Logo({
  className,
  showVersion = true,
}: {
  className?: string;
  showVersion?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <SealMark size={30} />
      <span className="font-display text-xl font-bold tracking-tight text-ink">
        {BRAND.name}
      </span>
      {showVersion && (
        <span className="rounded bg-brand px-1.5 py-0.5 text-[10px] font-semibold text-white">
          {BRAND.version}
        </span>
      )}
    </div>
  );
}
