"use client";

import { motion } from "framer-motion";
import { ArrowRight, Download } from "lucide-react";
import { company, heroBadges, pillars } from "@/lib/content";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

const fadeUp = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
};

export function Hero() {
  return (
    <section
      id="hero"
      className="relative min-h-[100svh] overflow-hidden border-b border-border pb-16 pt-24 md:pb-24 md:pt-28"
    >
      <div aria-hidden="true" className="absolute inset-0 -z-10 grid-bg" />
      <div aria-hidden="true" className="absolute inset-0 -z-10 gradient-radial-accent" />

      <div className="container">
        <motion.div
          {...fadeUp}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        >
          <Badge variant="default">{company.positioningBadge}</Badge>
        </motion.div>

        <motion.h1
          {...fadeUp}
          transition={{ duration: 0.7, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
          className="mt-6 max-w-[18ch] font-display text-display-xl font-bold leading-[1.05] tracking-tight"
        >
          Сайт как актив. <br />
          <span className="text-accent">Digital как процесс.</span>
        </motion.h1>

        <motion.p
          {...fadeUp}
          transition={{ duration: 0.7, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
          className="mt-6 max-w-2xl text-base leading-relaxed text-text/90 md:text-lg"
        >
          {company.shortPitch}
        </motion.p>

        <motion.p
          {...fadeUp}
          transition={{ duration: 0.7, delay: 0.18, ease: [0.22, 1, 0.36, 1] }}
          className="mt-3 max-w-2xl text-sm text-muted md:text-[15px]"
        >
          {company.antiPromise}
        </motion.p>

        <motion.div
          {...fadeUp}
          transition={{ duration: 0.7, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="mt-9 flex flex-wrap gap-3"
        >
          <Button href="#cta" variant="primary" size="lg">
            Обсудить проект
            <ArrowRight size={18} strokeWidth={1.8} aria-hidden="true" />
          </Button>
          <Button href="#cta" variant="outline" size="lg">
            <Download size={18} strokeWidth={1.6} aria-hidden="true" />
            Скачать кит
          </Button>
        </motion.div>

        <motion.ul
          {...fadeUp}
          transition={{ duration: 0.7, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-3 text-xs uppercase tracking-[0.14em] text-muted md:text-[13px]"
        >
          {heroBadges.map((badge, i) => (
            <li key={badge} className="flex items-center gap-3">
              <span aria-hidden="true" className="h-1 w-1 rounded-full bg-accent" />
              <span>{badge}</span>
              {i < heroBadges.length - 1 && (
                <span aria-hidden="true" className="hidden h-3 w-px bg-border md:block" />
              )}
            </li>
          ))}
        </motion.ul>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="mt-14 grid gap-4 border-t border-border pt-10 md:mt-20 md:grid-cols-3"
        >
          {pillars.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border text-accent">
                <Icon size={18} strokeWidth={1.6} aria-hidden="true" />
              </div>
              <div>
                <p className="font-display text-base font-bold text-text">{title}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
              </div>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
