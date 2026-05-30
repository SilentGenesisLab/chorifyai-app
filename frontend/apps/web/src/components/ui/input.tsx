import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-11 w-full rounded-lg border border-border bg-surface px-3.5 text-sm outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/25",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
