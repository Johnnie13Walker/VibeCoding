import { ArrowUpRight } from "lucide-react";
import type { Service } from "@/lib/content";
import { Card } from "./Card";

export function ServiceCard({ service }: { service: Service }) {
  const Icon = service.icon;
  return (
    <Card className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-bg text-accent transition-colors duration-300 group-hover:border-accent/60">
          <Icon size={22} strokeWidth={1.6} aria-hidden="true" />
        </div>
        <span className="text-sm font-medium text-accent">{service.price}</span>
      </div>

      <h3 className="mt-6 font-display text-2xl font-bold text-text md:text-[1.65rem]">
        {service.title}
      </h3>

      <p className="mt-3 text-[15px] leading-relaxed text-muted">{service.utp}</p>

      <p className="mt-5 rounded-xl border border-border bg-bg/40 p-4 text-[13px] leading-relaxed text-text/80">
        <span className="text-muted">Доказательство. </span>
        {service.proof}
      </p>

      <div className="mt-auto flex items-center justify-between pt-6">
        <span className="text-xs uppercase tracking-[0.14em] text-muted">
          {service.duration ?? "По запросу"}
        </span>
        <a
          href="#cta"
          className="inline-flex items-center gap-1 text-sm font-medium text-text transition-colors duration-200 hover:text-accent"
          aria-label={`Подробнее об услуге: ${service.title}`}
        >
          Подробнее
          <ArrowUpRight size={16} strokeWidth={1.8} aria-hidden="true" />
        </a>
      </div>
    </Card>
  );
}
