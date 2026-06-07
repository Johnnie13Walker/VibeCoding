'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Users } from 'lucide-react';
import {
  aggregateTmMonthlyPeriod,
  aggregateTmMonthlyRows,
  buildTmMonthly,
  type TmMonthlyBundle,
  type TmMonthlyPeriod,
} from '@/lib/telemarketing-shared';
import { TmMonthlyView } from './blocks';

const nf = (n: number) => new Intl.NumberFormat('ru-RU').format(n);

const FiredTag = () => (
  <span style={{
    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.03em',
    color: 'var(--bb-faint)', background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)',
    borderRadius: 999, padding: '1px 7px', flex: '0 0 auto',
  }}>уволен</span>
);

// Мультиселект звонарей — паттерн из TmFunnel.tsx (ManagerPicker).
function ManagerPicker({
  managers, selected, onChange,
}: {
  managers: { managerId: number; name: string; isActive: boolean }[];
  selected: Set<number>;
  onChange: (s: Set<number>) => void;
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
  const label = n === 0 ? 'Никто не выбран' : n === all ? `Все звонари (${all})` : `Выбрано: ${n} из ${all}`;
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

// Полоса сравнения «на эту дату»: текущий vs прошлый месяц на ту же дату 1..N.
function CompareCell({ title, cur, prev }: { title: string; cur: number; prev: number }) {
  const delta = cur - prev;
  const tone = delta > 0 ? { c: 'var(--bb-green)', s: '+' } : delta < 0 ? { c: 'var(--bb-red)', s: '' } : { c: 'var(--bb-faint)', s: '' };
  return (
    <div style={{ background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 13, padding: '12px 14px', boxShadow: 'var(--bb-shadow)' }}>
      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--bb-faint)', fontWeight: 600 }}>{title}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
        <span className="tabular" style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1 }}>{nf(cur)}</span>
        <span className="tabular" style={{ fontSize: 12.5, fontWeight: 700, color: tone.c }}>{tone.s}{nf(delta)}</span>
      </div>
      <div className="tabular" style={{ fontSize: 11.5, color: 'var(--bb-muted)', marginTop: 4 }}>было {nf(prev)}</div>
    </div>
  );
}

function CompareBar({ cur, prev, curLabel, prevLabel }: { cur: TmMonthlyPeriod; prev: TmMonthlyPeriod; curLabel: string; prevLabel: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 10, color: 'var(--bb-ink)' }}>
        На эту дату · <span style={{ color: 'var(--bb-violet)' }}>{curLabel}</span>
        <span style={{ color: 'var(--bb-faint)', fontWeight: 500 }}> vs прошлый месяц ({prevLabel})</span>
      </div>
      <div className="bb-grid bb-grid-4">
        <CompareCell title="Набрано" cur={cur.dials} prev={prev.dials} />
        <CompareCell title="Дозвоны ≥60с" cur={cur.calls60} prev={prev.calls60} />
        <CompareCell title="Встречи назн." cur={cur.meetingsSet} prev={prev.meetingsSet} />
        <CompareCell title="Состоялось" cur={cur.held} prev={prev.held} />
      </div>
    </div>
  );
}

export function TmMonthly({ data }: { data: TmMonthlyBundle }) {
  const allIds = useMemo(() => data.selectableManagers.map((m) => m.managerId), [data.selectableManagers]);
  const [selected, setSelected] = useState<Set<number>>(() => new Set(allIds));

  const rows = useMemo(
    () => buildTmMonthly(aggregateTmMonthlyRows(data.perManager, selected, data.months)),
    [data.perManager, data.months, selected],
  );
  const period = useMemo(
    () => aggregateTmMonthlyPeriod(data.perManager, selected),
    [data.perManager, selected],
  );

  const all = data.selectableManagers.length;
  const n = selected.size;
  const name =
    n === 0 ? null
      : n === all ? 'все звонари'
        : data.selectableManagers.filter((m) => selected.has(m.managerId)).map((m) => m.name).join(', ');

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14, marginTop: -4 }}>
        <ManagerPicker managers={data.selectableManagers} selected={selected} onChange={setSelected} />
      </div>
      {data.curLabel ? (
        <CompareBar cur={period.cur} prev={period.prev} curLabel={data.curLabel} prevLabel={data.prevLabel} />
      ) : null}
      {n === 0 ? (
        <p style={{ color: 'var(--bb-muted)' }}>Выберите звонарей в фильтре, чтобы увидеть динамику.</p>
      ) : (
        <TmMonthlyView rows={rows} name={name} />
      )}
    </div>
  );
}
