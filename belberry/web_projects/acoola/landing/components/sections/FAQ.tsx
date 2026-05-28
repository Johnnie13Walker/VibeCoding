"use client";

import { Plus, Minus } from "lucide-react";
import { useState } from "react";
import { faq } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

export function FAQ() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="section border-b border-border">
      <div className="container max-w-4xl">
        <div className="text-center">
          <Badge variant="accent">FAQ</Badge>
          <h2 className="mt-5 font-display text-display-lg font-bold leading-tight">
            Шесть вопросов, которые задают на первом созвоне.
          </h2>
        </div>

        <ul className="mt-12 grid gap-3">
          {faq.map((item, i) => {
            const isOpen = open === i;
            return (
              <li
                key={item.q}
                className={cn(
                  "rounded-2xl border bg-surface transition-colors duration-300",
                  isOpen ? "border-accent/50" : "border-border",
                )}
              >
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={`faq-${i}`}
                  onClick={() => setOpen(isOpen ? null : i)}
                  className="flex w-full items-center justify-between gap-6 px-6 py-5 text-left transition-colors hover:text-accent"
                >
                  <span className="font-display text-base font-bold text-text md:text-lg">
                    {item.q}
                  </span>
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-accent">
                    {isOpen ? <Minus size={16} /> : <Plus size={16} />}
                  </span>
                </button>
                <div
                  id={`faq-${i}`}
                  hidden={!isOpen}
                  className="px-6 pb-6 text-[15px] leading-relaxed text-muted"
                >
                  {item.a}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
