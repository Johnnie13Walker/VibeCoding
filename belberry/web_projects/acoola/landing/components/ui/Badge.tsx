import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "accent";
};

export function Badge({ className, variant = "default", children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs uppercase tracking-[0.14em]",
        variant === "default"
          ? "border-border text-muted"
          : "border-accent/40 text-accent bg-accent/5",
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
