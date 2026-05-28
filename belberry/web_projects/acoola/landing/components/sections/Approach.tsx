import { approach } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";

export function Approach() {
  return (
    <section id="approach" className="section border-b border-border">
      <div className="container">
        <div className="max-w-3xl">
          <Badge variant="accent">Подход</Badge>
          <h2 className="mt-5 font-display text-display-lg font-bold leading-tight">
            Пять шагов, после которых проект становится управляемым.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-muted md:text-lg">
            Никаких «сначала запустимся, потом разберёмся». На втором шаге вы уже знаете, какие
            метрики растут — и в какой срок.
          </p>
        </div>

        <ol className="relative mt-16 grid gap-6 md:grid-cols-5">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-0 right-0 top-6 hidden h-px bg-gradient-to-r from-transparent via-border to-transparent md:block"
          />
          {approach.map((step) => (
            <li
              key={step.n}
              className="relative rounded-2xl border border-border bg-surface p-6 transition-colors duration-300 hover:border-accent/50"
            >
              <span className="font-display text-sm font-bold tracking-[0.2em] text-accent">
                {step.n}
              </span>
              <h3 className="mt-4 font-display text-lg font-bold text-text md:text-xl">
                {step.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
