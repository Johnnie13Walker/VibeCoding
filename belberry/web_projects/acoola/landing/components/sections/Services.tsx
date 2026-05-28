import { services } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";
import { ServiceCard } from "@/components/ui/ServiceCard";

export function Services() {
  return (
    <section id="services" className="section border-b border-border">
      <div className="container">
        <div className="max-w-3xl">
          <Badge variant="accent">Услуги</Badge>
          <h2 className="mt-5 font-display text-display-lg font-bold leading-tight">
            Восемь направлений — одна команда и один прогресс по проекту.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-muted md:text-lg">
            Не дробим результат между подрядчиками. Каждое направление — со своей экспертизой и
            сертификациями. Без переключений и согласований между внешними студиями.
          </p>
        </div>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {services.map((s) => (
            <ServiceCard key={s.id} service={s} />
          ))}
        </div>
      </div>
    </section>
  );
}
