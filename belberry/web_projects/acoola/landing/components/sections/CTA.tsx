"use client";

import { ArrowRight, Download, Mail, MapPin, Phone } from "lucide-react";
import { useState } from "react";
import { contacts } from "@/lib/content";
import { Button } from "@/components/ui/Button";

function formatPhone(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  const trimmed = digits.startsWith("8") || digits.startsWith("7") ? digits.slice(1) : digits;
  const parts = ["+7"];
  if (trimmed.length > 0) parts.push(` (${trimmed.slice(0, 3)}`);
  if (trimmed.length >= 3) parts.push(")");
  if (trimmed.length >= 4) parts.push(` ${trimmed.slice(3, 6)}`);
  if (trimmed.length >= 7) parts.push(`-${trimmed.slice(6, 8)}`);
  if (trimmed.length >= 9) parts.push(`-${trimmed.slice(8, 10)}`);
  return parts.join("");
}

export function CTA() {
  const [submitted, setSubmitted] = useState(false);
  const [phone, setPhone] = useState("");

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    // TODO: подключить реальный обработчик формы (CRM/почта)
    console.info("[CTA] form submit", data);
    setSubmitted(true);
  };

  return (
    <section id="cta" className="relative overflow-hidden border-b border-border">
      <div aria-hidden="true" className="absolute inset-0 -z-10 gradient-radial-cta" />

      <div className="container section">
        <div className="grid gap-14 lg:grid-cols-[1.1fr,1fr]">
          <div>
            <h2 className="font-display text-display-lg font-bold leading-tight">
              Расскажите про <span className="text-accent">ваш проект</span>.
            </h2>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-muted md:text-lg">
              30-минутный разговор — и вы поймёте, есть ли смысл работать вместе. На встрече покажем
              релевантные кейсы из вашей отрасли и обозначим, какие метрики можно сдвинуть в первые
              1–3 месяца.
            </p>

            <div className="mt-10 grid gap-5 md:max-w-md">
              <ContactRow icon={<MapPin size={18} aria-hidden="true" />}>
                {contacts.city}, {contacts.address}
              </ContactRow>
              <ContactRow icon={<Phone size={18} aria-hidden="true" />}>
                <a href={contacts.phoneHref} className="hover:text-accent">
                  {contacts.phone}
                </a>
              </ContactRow>
              <ContactRow icon={<Mail size={18} aria-hidden="true" />}>
                <a href={contacts.emailHref} className="hover:text-accent">
                  {contacts.email}
                </a>
              </ContactRow>
            </div>

            <div className="mt-8">
              <Button href="#" variant="outline" size="md">
                <Download size={16} aria-hidden="true" />
                Скачать маркетинг-кит в PDF
              </Button>
            </div>
          </div>

          {submitted ? (
            <div
              role="status"
              aria-live="polite"
              className="flex flex-col justify-center rounded-3xl border border-accent/40 bg-surface p-8 md:p-10"
            >
              <p className="font-display text-2xl font-bold text-text">Заявка отправлена.</p>
              <p className="mt-3 text-base leading-relaxed text-muted">
                В течение рабочего дня менеджер свяжется и предложит удобное время для созвона. Если
                это срочно — напишите на{" "}
                <a href={contacts.emailHref} className="text-accent hover:underline">
                  {contacts.email}
                </a>
                .
              </p>
            </div>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-4 rounded-3xl border border-border bg-surface p-7 md:p-9"
              aria-label="Форма заявки на проект"
              noValidate
            >
              <Field
                label="Как вас зовут"
                name="name"
                type="text"
                autoComplete="name"
                required
              />
              <Field
                label="Телефон"
                name="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(formatPhone(e.target.value))}
                placeholder="+7 (___) ___-__-__"
                required
              />
              <Field
                label="Email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="name@company.ru"
              />
              <FieldArea label="Кратко о задаче" name="task" rows={4} />

              <Button type="submit" variant="primary" size="lg" className="mt-2 w-full">
                Отправить заявку
                <ArrowRight size={18} aria-hidden="true" />
              </Button>
              <p className="text-xs leading-relaxed text-muted">
                Нажимая кнопку, вы соглашаетесь с обработкой персональных данных. Никакого спама —
                только по делу.
              </p>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}

function ContactRow({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 text-sm text-text/90 md:text-[15px]">
      <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl border border-border text-accent">
        {icon}
      </span>
      <span className="leading-relaxed">{children}</span>
    </div>
  );
}

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & { label: string; name: string };

function Field({ label, name, ...rest }: FieldProps) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="text-xs uppercase tracking-[0.14em] text-muted">{label}</span>
      <input
        name={name}
        className="h-12 rounded-xl border border-border bg-bg px-4 text-base text-text outline-none transition-colors focus:border-accent"
        {...rest}
      />
    </label>
  );
}

type FieldAreaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; name: string };

function FieldArea({ label, name, ...rest }: FieldAreaProps) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="text-xs uppercase tracking-[0.14em] text-muted">{label}</span>
      <textarea
        name={name}
        className="rounded-xl border border-border bg-bg px-4 py-3 text-base text-text outline-none transition-colors focus:border-accent resize-y"
        {...rest}
      />
    </label>
  );
}
