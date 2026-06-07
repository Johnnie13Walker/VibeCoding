'use client';

import { useMemo, useState } from 'react';
import {
  aggregateTmMonthlyPeriod,
  aggregateTmMonthlyRows,
  buildTmMonthly,
  type TmMonthlyBundle,
  type TmMonthlyPeriod,
} from '@/lib/telemarketing-shared';
import { ManagerPicker } from './ManagerPicker';
import { TmMonthlyView } from './blocks';

const nf = (n: number) => new Intl.NumberFormat('ru-RU').format(n);

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
