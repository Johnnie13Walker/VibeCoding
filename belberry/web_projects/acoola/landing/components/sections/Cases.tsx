import { cases } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";
import { CaseCard } from "@/components/ui/CaseCard";

export function Cases() {
  return (
    <section id="cases" className="section border-b border-border">
      <div className="container">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <Badge variant="accent">Кейсы</Badge>
            <h2 className="mt-5 font-display text-display-lg font-bold leading-tight">
              Цифры, которые можно проверить — выручка, ROI, стоимость лида.
            </h2>
          </div>
          <p className="max-w-md text-sm leading-relaxed text-muted md:text-[15px]">
            Каждый кейс — про бизнес-метрики. Без «трафик вырос» без указания на что и относительно
            какого периода.
          </p>
        </div>

        <div className="mt-14 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {cases.map((c) => (
            <CaseCard key={c.id} data={c} />
          ))}
        </div>
      </div>
    </section>
  );
}
