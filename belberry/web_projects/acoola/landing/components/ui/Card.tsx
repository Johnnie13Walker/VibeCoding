import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "group relative rounded-2xl border border-border bg-surface p-6 md:p-7 transition-all duration-300 hover:-translate-y-0.5 hover:border-accent/50",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
