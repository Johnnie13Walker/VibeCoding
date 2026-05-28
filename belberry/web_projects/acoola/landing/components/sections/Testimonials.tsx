"use client";

import { useCallback, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Quote } from "lucide-react";
import { testimonials } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

export function Testimonials() {
  const [index, setIndex] = useState(0);
  const total = testimonials.length;
  const touchStart = useRef<number | null>(null);

  const go = useCallback(
    (dir: 1 | -1) => {
      setIndex((i) => (i + dir + total) % total);
    },
    [total],
  );

  return (
    <section id="testimonials" className="section border-b border-border">
      <div className="container">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <Badge variant="accent">Отзывы</Badge>
            <h2 className="mt-5 font-display text-display-lg font-bold leading-tight">
              Шесть клиентов — про работу, продолжающуюся годами.
            </h2>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Предыдущий отзыв"
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-border text-text transition-colors hover:border-accent hover:text-accent"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Следующий отзыв"
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-border text-text transition-colors hover:border-accent hover:text-accent"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>

        <div
          className="mt-12 overflow-hidden rounded-3xl border border-border bg-surface"
          onTouchStart={(e) => {
            touchStart.current = e.touches[0].clientX;
          }}
          onTouchEnd={(e) => {
            if (touchStart.current === null) return;
            const delta = e.changedTouches[0].clientX - touchStart.current;
            if (Math.abs(delta) > 40) go(delta < 0 ? 1 : -1);
            touchStart.current = null;
          }}
        >
          <div
            className="flex transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{ transform: `translateX(-${index * 100}%)` }}
            aria-live="polite"
          >
            {testimonials.map((t) => (
              <article
                key={t.company}
                className="flex w-full shrink-0 flex-col gap-6 p-8 md:p-12"
              >
                <Quote
                  size={32}
                  strokeWidth={1.5}
                  aria-hidden="true"
                  className="text-accent"
                />
                <p className="max-w-3xl font-display text-xl leading-snug text-text md:text-2xl">
                  «{t.quote}»
                </p>
                <div className="mt-2">
                  <p className="font-display text-base font-bold text-text">{t.company}</p>
                  <p className="text-sm text-muted">{t.author}</p>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="mt-6 flex justify-center gap-2">
          {testimonials.map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Перейти к отзыву ${i + 1}`}
              aria-current={i === index}
              onClick={() => setIndex(i)}
              className={cn(
                "h-1.5 rounded-full transition-all duration-300",
                i === index ? "w-8 bg-accent" : "w-3 bg-border hover:bg-muted",
              )}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
