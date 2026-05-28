import { awards } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";

export function Awards() {
  return (
    <section className="section-tight border-b border-border" aria-labelledby="awards-title">
      <div className="container">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <Badge variant="default">Награды и статусы</Badge>
            <h2
              id="awards-title"
              className="mt-5 font-display text-display-md font-bold leading-tight md:text-[1.9rem]"
            >
              Внешние оценки, которые мы не присваивали себе сами.
            </h2>
          </div>
        </div>

        <ul className="mt-10 grid grid-cols-2 gap-3 md:grid-cols-4">
          {awards.map((a) => (
            <li
              key={a.title}
              className="flex h-full items-center rounded-xl border border-border bg-surface px-4 py-4 text-[13px] leading-snug text-text/85 md:text-sm"
            >
              {a.title}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
