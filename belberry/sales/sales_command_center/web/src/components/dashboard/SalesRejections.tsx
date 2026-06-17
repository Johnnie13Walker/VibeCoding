'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Users } from 'lucide-react';
import {
  aggregateSelected,
  managersFromPerManager,
  type SalesRejectionsBundle,
  type SelectableManager,
} from '@/lib/sales-rejections-shared';

const FiredTag = () => (
  <span style={{
    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.03em',
    color: 'var(--bb-faint)', background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)',
    borderRadius: 999, padding: '1px 7px', flex: '0 0 auto',
  }}>уволен</span>
);

function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase() || '—';
}

/** Бейдж «доли отказов»: высокая = плохо (красный), средняя — amber, низкая — зелёный. */
function rateBadge(pct: number | null): React.CSSProperties {
  const base: React.CSSProperties = {
    display: 'inline-block', fontSize: 12, fontWeight: 700, borderRadius: 999, padding: '3px 9px',
  };
  if (pct == null) return { ...base, background: 'var(--bb-violet-soft)', color: 'var(--bb-muted)' };
  if (pct >= 40) return { ...base, background: '#fdeced', color: 'var(--bb-red)' };
  if (pct >= 25) return { ...base, background: '#fdf2e7', color: '#b5651d' };
  return { ...base, background: '#e7f4ec', color: 'var(--bb-green)' };
}

const kpi = (value: string, label: string, sub: string, red = false) => (
  <div style={{ background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)', borderRadius: 14, padding: '14px 16px' }}>
    <div className="tabular" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.02em', color: red ? 'var(--bb-red)' : 'var(--bb-ink)' }}>{value}</div>
    <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 4 }}>{label}</div>
    <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 4 }}>{sub}</div>
  </div>
);

/** Выпадающий чек-лист менеджеров ОП. */
function ManagerPicker({
  managers, selected, onChange,
}: {
  managers: SelectableManager[];
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
  const label = n === 0 ? 'Никто не выбран' : n === all ? `Все менеджеры (${all})` : `Выбрано: ${n} из ${all}`;

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(next);
  };

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--bb-line)',
          background: '#fff', borderRadius: 11, padding: '8px 12px', font: 'inherit', fontSize: 13,
          fontWeight: 600, color: 'var(--bb-ink)', cursor: 'pointer',
        }}
      >
        <Users size={15} style={{ color: 'var(--bb-violet)' }} />
        {label}
        <ChevronDown size={15} style={{ color: 'var(--bb-faint)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
      </button>

      {open ? (
        <div
          style={{
            position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 20, width: 280,
            background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 14,
            boxShadow: 'var(--bb-shadow-lift)', padding: 8, maxHeight: 360, overflow: 'auto',
          }}
        >
          <div style={{ display: 'flex', gap: 6, padding: '4px 6px 8px', borderBottom: '1px solid var(--bb-line)', marginBottom: 6 }}>
            <button type="button" onClick={() => onChange(new Set(managers.map((m) => m.managerId)))}
              style={{ flex: 1, border: '1px solid var(--bb-line)', background: 'var(--bb-canvas)', borderRadius: 8, padding: '5px 8px', font: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: 'var(--bb-violet)' }}>
              Выбрать всех
            </button>
            <button type="button" onClick={() => onChange(new Set())}
              style={{ flex: 1, border: '1px solid var(--bb-line)', background: 'var(--bb-canvas)', borderRadius: 8, padding: '5px 8px', font: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: 'var(--bb-muted)' }}>
              Снять всё
            </button>
          </div>
          {managers.map((m) => {
            const on = selected.has(m.managerId);
            return (
              <button
                key={m.managerId}
                type="button"
                onClick={() => toggle(m.managerId)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 10px',
                  borderRadius: 10, border: 0, background: on ? 'var(--bb-violet-soft)' : 'transparent',
                  font: 'inherit', fontSize: 13.5, color: 'var(--bb-ink)', cursor: 'pointer', textAlign: 'left',
                }}
              >
                <span style={{
                  width: 18, height: 18, flex: '0 0 18px', borderRadius: 6, display: 'grid', placeItems: 'center',
                  border: on ? '0' : '1.5px solid var(--bb-line)', background: on ? 'var(--bb-violet)' : '#fff',
                }}>
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

/** Карточка 1 — динамика с начала года с мультиселектом менеджеров. */
export function SalesRejectionsView({ data }: { data: SalesRejectionsBundle }) {
  const allIds = useMemo(() => data.selectableManagers.map((m) => m.managerId), [data.selectableManagers]);
  const [selected, setSelected] = useState<Set<number>>(() => new Set(allIds));

  const view = useMemo(
    () => aggregateSelected(data.perManager, selected, data.monthsSkeleton, data.yearLabel),
    [data.perManager, data.monthsSkeleton, data.yearLabel, selected],
  );

  const maxMonth = Math.max(...view.months.map((m) => m.count), 1);
  const maxReason = Math.max(...view.reasons.map((r) => r.count), 1);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14, marginTop: -4 }}>
        <ManagerPicker managers={data.selectableManagers} selected={selected} onChange={setSelected} />
      </div>

      {/* KPI */}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 20 }}>
        {kpi(String(view.totalRejections), 'Отказов всего', `${view.yearLabel} · без СПАМа`, true)}
        {kpi(rub(view.lostAmount), 'Потеряно', 'сумма проигранных сделок', true)}
        {kpi(view.lossRate != null ? `${view.lossRate}%` : '—', 'Доля отказов', 'отказы / (отказы + оплаты)')}
        {kpi(rub(view.avgLoss), 'Средняя потеря', 'на одну сделку')}
      </div>

      {/* Помесячно */}
      <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Отказы по месяцам</h4>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 150, padding: '6px 4px 0', borderBottom: '1px solid var(--bb-line)', marginBottom: 8 }}>
        {view.months.map((m) => (
          <div key={m.ym} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, height: '100%', justifyContent: 'flex-end' }}>
            <span className="tabular" style={{ fontSize: 13, fontWeight: 800 }}>{m.count}</span>
            <div style={{ width: '100%', maxWidth: 46, height: `${Math.max(3, (m.count / maxMonth) * 100)}%`, borderRadius: '8px 8px 0 0', background: 'linear-gradient(180deg,#e88a3b,#d4202e)' }} />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 12, padding: '0 4px' }}>
        {view.months.map((m) => (
          <span key={m.ym} style={{ flex: 1, textAlign: 'center', fontSize: 12, color: 'var(--bb-muted)', fontWeight: 500 }}>{m.label}</span>
        ))}
      </div>

      {/* Причины */}
      <h4 style={{ fontSize: 13, fontWeight: 700, margin: '22px 0 10px' }}>Причины отказов</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {view.reasons.map((r) => (
          <div key={`${r.reasonId}`} style={{ display: 'grid', gridTemplateColumns: '210px 1fr 96px', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 13, color: 'var(--bb-ink)', fontWeight: 500 }}>{r.label}</span>
            <div style={{ height: 22, background: '#f3f0ec', borderRadius: 7, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.max(4, (r.count / maxReason) * 100)}%`, borderRadius: 7, background: 'linear-gradient(90deg,#f0a35a,#d4202e)' }} />
            </div>
            <span className="tabular" style={{ textAlign: 'right', fontSize: 12.5, fontWeight: 700 }}>
              {r.count} <span style={{ color: 'var(--bb-faint)', fontWeight: 600 }}>· {r.pct}%</span>
            </span>
          </div>
        ))}
        {view.reasons.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--bb-faint)' }}>Нет отказов по выбранным менеджерам за период.</div>
        ) : null}
      </div>

      {view.spamExcluded > 0 ? (
        <div style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 12, paddingTop: 10, borderTop: '1px dashed var(--bb-line)' }}>
          + {view.spamExcluded} СПАМ-{view.spamExcluded === 1 ? 'лид' : 'лидов'} отсеяно — нецелевые, в отказы и «долю» не входят.
        </div>
      ) : null}
    </div>
  );
}

/** Карточка 2 — отказы по менеджерам (все действующие продажники). */
export function SalesRejectionsManagers({ data }: { data: SalesRejectionsBundle }) {
  const managers = data.managers.length ? data.managers : managersFromPerManager(data.perManager);
  const maxAmount = Math.max(...managers.map((m) => m.lostAmount), 1);
  const totalRej = managers.reduce((a, m) => a + m.rejections, 0);
  const totalLost = managers.reduce((a, m) => a + m.lostAmount, 0);
  const totalWon = managers.reduce((a, m) => a + m.won, 0);
  const totalRate = totalRej + totalWon > 0 ? Math.round((totalRej / (totalRej + totalWon)) * 100) : null;

  if (managers.length === 0) {
    return <div style={{ fontSize: 13, color: 'var(--bb-faint)' }}>Отказов с начала года не зафиксировано.</div>;
  }

  const ttop = { borderTop: '2px solid var(--bb-line)' } as React.CSSProperties;
  return (
    <table className="bb-table tabular">
      <thead>
        <tr>
          <th>Менеджер</th>
          <th className="r">Отказов</th>
          <th className="r">Потеряно ₽</th>
          <th className="r">Доля отказов</th>
          <th>Топ-причина</th>
        </tr>
      </thead>
      <tbody>
        {managers.map((m) => (
          <tr key={m.managerId}>
            <td>
              <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                <div className="bb-mrow-ava" style={{ width: 34, height: 34, flex: '0 0 34px', fontSize: 12 }}>{initials(m.name)}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <b style={{ fontSize: 14, fontWeight: 600 }}>{m.name}</b>
                  {m.isActive ? null : <FiredTag />}
                </div>
              </div>
            </td>
            <td className="r">{m.rejections}</td>
            <td className="r">
              {rub(m.lostAmount)}
              <div style={{ height: 7, borderRadius: 6, background: '#f0ece7', overflow: 'hidden', maxWidth: 160, marginTop: 5, marginLeft: 'auto' }}>
                <i style={{ display: 'block', height: '100%', width: `${(m.lostAmount / maxAmount) * 100}%`, borderRadius: 6, background: 'linear-gradient(90deg,#e88a3b,#d4202e)' }} />
              </div>
            </td>
            <td className="r">
              <span style={rateBadge(m.lossRate)}>{m.lossRate != null ? `${m.lossRate}%` : '—'}</span>
            </td>
            <td><span style={{ fontSize: 11.5, color: 'var(--bb-muted)' }}>{m.topReason ?? '—'}</span></td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td style={{ fontWeight: 800, ...ttop }}>Итого по действующим</td>
          <td className="r" style={{ fontWeight: 800, ...ttop }}>{totalRej}</td>
          <td className="r" style={{ fontWeight: 800, ...ttop }}>{rub(totalLost)}</td>
          <td className="r" style={{ fontWeight: 800, ...ttop }}>{totalRate != null ? `${totalRate}%` : '—'}</td>
          <td style={ttop} />
        </tr>
      </tfoot>
    </table>
  );
}
