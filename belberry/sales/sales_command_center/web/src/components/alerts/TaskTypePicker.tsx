'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Filter } from 'lucide-react';
import type { TaskKind } from '@/lib/alerts-filter';

const KINDS: { id: TaskKind; name: string; dot: string }[] = [
  { id: 'overdue', name: 'В просрочке', dot: '#d4202e' },
  { id: 'control', name: 'На контроле', dot: '#1a7f37' },
  { id: 'await', name: 'Ждёт выполнения', dot: '#5b50d6' },
];

/** Мультивыбор задач по типу (просрочка / контроль / ждёт). Зеркалит ManagerPicker. */
export function TaskTypePicker({ selected, onChange }: { selected: Set<TaskKind>; onChange: (s: Set<TaskKind>) => void }) {
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

  const all = KINDS.length;
  const n = selected.size;
  const label = n === 0 ? 'Тип не выбран' : n === all ? `Все типы (${all})` : `Выбрано: ${n} из ${all}`;
  const toggle = (id: TaskKind) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(next);
  };

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--bb-line)', background: '#fff', borderRadius: 11, padding: '8px 12px', font: 'inherit', fontSize: 13, fontWeight: 600, color: 'var(--bb-ink)', cursor: 'pointer' }}>
        <Filter size={15} style={{ color: 'var(--bb-violet)' }} />
        {label}
        <ChevronDown size={15} style={{ color: 'var(--bb-faint)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
      </button>
      {open ? (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 20, width: 240, background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 14, boxShadow: 'var(--bb-shadow-lift)', padding: 8 }}>
          <div style={{ display: 'flex', gap: 6, padding: '4px 6px 8px', borderBottom: '1px solid var(--bb-line)', marginBottom: 6 }}>
            <button type="button" onClick={() => onChange(new Set(KINDS.map((k) => k.id)))}
              style={{ flex: 1, border: '1px solid var(--bb-line)', background: 'var(--bb-canvas)', borderRadius: 8, padding: '5px 8px', font: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: 'var(--bb-violet)' }}>Выбрать все</button>
            <button type="button" onClick={() => onChange(new Set())}
              style={{ flex: 1, border: '1px solid var(--bb-line)', background: 'var(--bb-canvas)', borderRadius: 8, padding: '5px 8px', font: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: 'var(--bb-muted)' }}>Снять всё</button>
          </div>
          {KINDS.map((k) => {
            const on = selected.has(k.id);
            return (
              <button key={k.id} type="button" onClick={() => toggle(k.id)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 10px', borderRadius: 10, border: 0, background: on ? 'var(--bb-violet-soft)' : 'transparent', font: 'inherit', fontSize: 13.5, color: 'var(--bb-ink)', cursor: 'pointer', textAlign: 'left' }}>
                <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 6, display: 'grid', placeItems: 'center', border: on ? '0' : '1.5px solid var(--bb-line)', background: on ? 'var(--bb-violet)' : '#fff' }}>
                  {on ? <Check size={13} color="#fff" /> : null}
                </span>
                <span style={{ width: 9, height: 9, flex: '0 0 9px', borderRadius: 999, background: k.dot }} />
                <span style={{ flex: 1 }}>{k.name}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
