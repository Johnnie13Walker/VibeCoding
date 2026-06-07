'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Users } from 'lucide-react';

export const FiredTag = () => (
  <span style={{
    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.03em',
    color: 'var(--bb-faint)', background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)',
    borderRadius: 999, padding: '1px 7px', flex: '0 0 auto',
  }}>уволен</span>
);

/** Выпадающий мультиселект сотрудников с тегом «уволен» и кнопками «Выбрать всех /
 * Снять всё». Общий для ТМ-воронки, динамики и карты набора. */
export function ManagerPicker({
  managers, selected, onChange, allWord = 'звонари',
}: {
  managers: { managerId: number; name: string; isActive: boolean }[];
  selected: Set<number>;
  onChange: (s: Set<number>) => void;
  /** Слово для подписи «Все … (N)»: «звонари» / «владельцы». */
  allWord?: string;
}) {
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

  const all = managers.length;
  const n = selected.size;
  const label = n === 0 ? 'Никто не выбран' : n === all ? `Все ${allWord} (${all})` : `Выбрано: ${n} из ${all}`;
  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(next);
  };

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--bb-line)', background: '#fff', borderRadius: 11, padding: '8px 12px', font: 'inherit', fontSize: 13, fontWeight: 600, color: 'var(--bb-ink)', cursor: 'pointer' }}>
        <Users size={15} style={{ color: 'var(--bb-violet)' }} />
        {label}
        <ChevronDown size={15} style={{ color: 'var(--bb-faint)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
      </button>
      {open ? (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 20, width: 280, background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 14, boxShadow: 'var(--bb-shadow-lift)', padding: 8, maxHeight: 360, overflow: 'auto' }}>
          <div style={{ display: 'flex', gap: 6, padding: '4px 6px 8px', borderBottom: '1px solid var(--bb-line)', marginBottom: 6 }}>
            <button type="button" onClick={() => onChange(new Set(managers.map((m) => m.managerId)))}
              style={{ flex: 1, border: '1px solid var(--bb-line)', background: 'var(--bb-canvas)', borderRadius: 8, padding: '5px 8px', font: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: 'var(--bb-violet)' }}>Выбрать всех</button>
            <button type="button" onClick={() => onChange(new Set())}
              style={{ flex: 1, border: '1px solid var(--bb-line)', background: 'var(--bb-canvas)', borderRadius: 8, padding: '5px 8px', font: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: 'var(--bb-muted)' }}>Снять всё</button>
          </div>
          {managers.map((m) => {
            const on = selected.has(m.managerId);
            return (
              <button key={m.managerId} type="button" onClick={() => toggle(m.managerId)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 10px', borderRadius: 10, border: 0, background: on ? 'var(--bb-violet-soft)' : 'transparent', font: 'inherit', fontSize: 13.5, color: 'var(--bb-ink)', cursor: 'pointer', textAlign: 'left' }}>
                <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 6, display: 'grid', placeItems: 'center', border: on ? '0' : '1.5px solid var(--bb-line)', background: on ? 'var(--bb-violet)' : '#fff' }}>
                  {on ? <Check size={13} color="#fff" /> : null}
                </span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</span>
                {m.isActive ? null : <FiredTag />}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
