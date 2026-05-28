import { stats } from "@/lib/content";
import { CountUp } from "@/components/ui/CountUp";

export function Stats() {
  return (
    <section className="section-tight border-b border-border" aria-labelledby="stats-title">
      <div className="container">
        <h2 id="stats-title" className="sr-only">
          Цифры агентства
        </h2>
        <div className="grid grid-cols-2 gap-x-6 gap-y-12 md:grid-cols-3 lg:grid-cols-5">
          {stats.map((s) => (
            <div key={s.label}>
              <p className="font-display text-stat font-extrabold text-accent">
                <CountUp
                  to={s.value}
                  prefix={s.prefix}
                  suffix={s.suffix}
                />
              </p>
              <p className="mt-3 text-sm leading-snug text-muted">{s.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
