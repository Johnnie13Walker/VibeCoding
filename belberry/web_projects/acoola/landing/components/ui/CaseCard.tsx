import { ArrowUpRight } from "lucide-react";
import type { CaseStudy } from "@/lib/content";
import { Badge } from "./Badge";
import { Card } from "./Card";

export function CaseCard({ data }: { data: CaseStudy }) {
  return (
    <Card className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3">
        <span className="font-display text-xl font-bold text-text">{data.client}</span>
        <Badge variant="accent">{data.serviceTag}</Badge>
      </div>
      <p className="mt-2 text-xs uppercase tracking-[0.14em] text-muted">{data.industry}</p>

      <h3 className="mt-6 font-display text-[1.4rem] font-bold leading-tight text-text md:text-[1.55rem]">
        {data.headline}
      </h3>

      <ul className="mt-5 grid gap-2">
        {data.metrics.map((m) => (
          <li
            key={m}
            className="flex items-start gap-2 text-[15px] text-text/85"
          >
            <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
            <span>{m}</span>
          </li>
        ))}
      </ul>

      <div className="mt-auto pt-7">
        <a
          href={data.href}
          className="inline-flex items-center gap-1 text-sm font-medium text-text transition-colors duration-200 hover:text-accent"
          aria-label={`Читать кейс: ${data.client}`}
        >
          Читать кейс
          <ArrowUpRight size={16} strokeWidth={1.8} aria-hidden="true" />
        </a>
      </div>
    </Card>
  );
}
