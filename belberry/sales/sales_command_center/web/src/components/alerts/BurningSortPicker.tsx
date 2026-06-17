'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowUpDown, ChevronDown } from 'lucide-react';
import type { BurnSort } from '@/lib/alerts-filter';

const OPTIONS: { id: BurnSort; name: string; short: string }[] = [
  { id: 'nomove', name: 'Дольше без движения', short: 'по простою' },
  { id: 'contact', name: 'Дольше без контакта', short: 'по контакту' },
];

/** Однозначный выбор сортировки секции «Горит». Стиль зеркалит ManagerPicker. */
export function BurningSortPicker({ value, onChange }: { value: BurnSort; onChange: (v: BurnSort) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const short = OPTIONS.find((o) => o.id === value)?.short ?? '';

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--bb-line)', background: '#fff', borderRadius: 11, padding: '8px 12px', font: 'inherit', fontSize: 13, fontWeight: 600, color: 'var(--bb-ink)', cursor: 'pointer' }}>
        <ArrowUpDown size={15} style={{ color: 'var(--bb-violet)' }} />
        Сортировка: {short}
        <ChevronDown size={15} style={{ color: 'var(--bb-faint)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
      </button>
      {open ? (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 20, width: 240, background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 14, boxShadow: 'var(--bb-shadow-lift)', padding: 8 }}>
          {OPTIONS.map((o) => {
            const on = o.id === value;
            return (
              <button key={o.id} type="button" onClick={() => { onChange(o.id); setOpen(false); }}
                style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 10px', borderRadius: 10, border: 0, background: on ? 'var(--bb-violet-soft)' : 'transparent', font: 'inherit', fontSize: 13.5, fontWeight: on ? 600 : 400, color: on ? 'var(--bb-violet)' : 'var(--bb-ink)', cursor: 'pointer', textAlign: 'left' }}>
                <span style={{ width: 16, height: 16, flex: '0 0 16px', borderRadius: 999, display: 'grid', placeItems: 'center', border: `1.5px solid ${on ? 'var(--bb-violet)' : 'var(--bb-line)'}` }}>
                  {on ? <span style={{ width: 8, height: 8, borderRadius: 999, background: 'var(--bb-violet)' }} /> : null}
                </span>
                <span style={{ flex: 1 }}>{o.name}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
