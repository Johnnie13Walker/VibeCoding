import { team } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";

export function Team() {
  return (
    <section id="team" className="section border-b border-border">
      <div className="container">
        <div className="max-w-3xl">
          <Badge variant="accent">Команда</Badge>
          <h2 className="mt-5 font-display text-display-lg font-bold leading-tight">
            50+ специалистов в&nbsp;6&nbsp;направлениях.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-muted md:text-lg">
            На каждом проекте закреплён менеджер и команда профильных специалистов. Состав
            фиксируется на старте и не меняется без согласования.
          </p>
        </div>

        <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {team.map((unit) => (
            <div
              key={unit.title}
              className="rounded-2xl border border-border bg-surface p-6 transition-colors hover:border-accent/50"
            >
              <h3 className="font-display text-xl font-bold text-text">{unit.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">{unit.certifications}</p>
            </div>
          ))}
        </div>

        {/* TODO: подтвердить распределение людей по направлениям и добавить численность */}
      </div>
    </section>
  );
}
