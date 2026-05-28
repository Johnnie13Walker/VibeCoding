import { company, contacts, nav, services } from "@/lib/content";

const company_links = [
  { label: "О нас", href: "#approach" },
  { label: "Команда", href: "#team" },
  { label: "Блог", href: "#" }, // TODO: ссылка на блог
  { label: "Вакансии", href: "#" }, // TODO: ссылка на hr-сайт
  { label: "Контакты", href: "#cta" },
];

const partner_links = [
  { label: "AcoolaShop", href: "#" }, // TODO: ссылка на AcoolaShop
  { label: "Партнёрская программа", href: "#" }, // TODO: ссылка на партнёрку
];

export function Footer() {
  return (
    <footer className="border-t border-border bg-bg">
      <div className="container py-16 md:py-20">
        <div className="grid gap-12 lg:grid-cols-[1.4fr,1fr,1fr,1fr,1fr]">
          <div>
            <p className="font-display text-2xl font-bold tracking-tight">{company.name}</p>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">
              {company.slogan}
            </p>
            <p className="mt-6 text-sm leading-relaxed text-text/85">
              {contacts.city}, {contacts.address}
            </p>
            <p className="mt-1 text-sm">
              <a href={contacts.phoneHref} className="text-text hover:text-accent">
                {contacts.phone}
              </a>
            </p>
            <p className="text-sm">
              <a href={contacts.emailHref} className="text-text hover:text-accent">
                {contacts.email}
              </a>
            </p>
          </div>

          <FooterColumn title="Услуги">
            {services.slice(0, 6).map((s) => (
              <FooterLink key={s.id} href="#services">
                {s.title}
              </FooterLink>
            ))}
          </FooterColumn>

          <FooterColumn title="Кейсы">
            {nav.slice(0, 4).map((item) => (
              <FooterLink key={item.href} href={item.href}>
                {item.label}
              </FooterLink>
            ))}
          </FooterColumn>

          <FooterColumn title="Компания">
            {company_links.map((l) => (
              <FooterLink key={l.label} href={l.href}>
                {l.label}
              </FooterLink>
            ))}
          </FooterColumn>

          <FooterColumn title="Партнёрам">
            {partner_links.map((l) => (
              <FooterLink key={l.label} href={l.href}>
                {l.label}
              </FooterLink>
            ))}
          </FooterColumn>
        </div>

        <div className="mt-14 flex flex-col gap-4 border-t border-border pt-8 text-xs text-muted md:flex-row md:items-center md:justify-between">
          <p>© 2026 {company.name}. Все права защищены.</p>
          <div className="flex gap-6">
            <a href="#" className="hover:text-accent">
              Политика конфиденциальности
            </a>
            <a href="#" className="hover:text-accent">
              Карта сайта
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs uppercase tracking-[0.16em] text-muted">{title}</h4>
      <ul className="mt-4 grid gap-2 text-sm">{children}</ul>
    </div>
  );
}

function FooterLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <li>
      <a href={href} className="text-text/85 transition-colors hover:text-accent">
        {children}
      </a>
    </li>
  );
}
