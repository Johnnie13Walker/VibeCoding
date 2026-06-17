'use client';

import { useMemo, useState } from 'react';
import { aggregateTmDialsHeatmap, type TmDialsHeatmapBundle } from '@/lib/telemarketing-shared';
import { ManagerPicker } from './ManagerPicker';

const nf = (n: number) => new Intl.NumberFormat('ru-RU').format(n);

export function TmDialsHeatmap({ data }: { data: TmDialsHeatmapBundle }) {
  const allIds = useMemo(() => data.selectableManagers.map((m) => m.managerId), [data.selectableManagers]);
  const [selected, setSelected] = useState<Set<number>>(() => new Set(allIds));

  const grid = useMemo(
    () => aggregateTmDialsHeatmap(data.perManager, selected, data.hours),
    [data.perManager, data.hours, selected],
  );

  const n = selected.size;
  // Цвет = интенсивность набора (чем темнее фиолетовый — тем больше звонят).
  const cellBg = (dials: number): string => {
    if (dials <= 0) return '#f6f4f1';
    const r = Math.min(1, dials / grid.maxDials);
    return `rgba(91, 80, 214, ${0.1 + r * 0.85})`;
  };
  const cellFg = (dials: number): string => {
    if (dials <= 0) return 'transparent';
    return dials / grid.maxDials > 0.45 ? '#fff' : 'var(--bb-ink)';
  };
  const cols = `34px repeat(${data.hours.length}, minmax(48px, 1fr))`;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14, marginTop: -4 }}>
        <ManagerPicker managers={data.selectableManagers} selected={selected} onChange={setSelected} />
      </div>
      {n === 0 || data.hours.length === 0 ? (
        <p style={{ color: 'var(--bb-muted)' }}>
          {n === 0 ? 'Выберите телемаркетологов в фильтре, чтобы увидеть карту набора.' : 'Нет данных о наборах за период.'}
        </p>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 5, minWidth: 760 }}>
              <div />
              {data.hours.map((h) => (
                <div key={`h${h}`} style={{ textAlign: 'center', fontSize: 11.5, color: 'var(--bb-faint)', fontWeight: 700, paddingBottom: 2 }}>{h}</div>
              ))}
              {grid.rows.map((row) => (
                <div key={`r${row.dow}`} style={{ display: 'contents' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', fontSize: 12.5, color: 'var(--bb-muted)', fontWeight: 700, paddingRight: 4 }}>{row.label}</div>
                  {row.cells.map((c) => (
                    <div
                      key={`${row.dow}-${c.hour}`}
                      title={`${row.label} ${c.hour}:00 — ${nf(c.dials)} наборов`}
                      style={{ height: 40, borderRadius: 9, background: cellBg(c.dials), display: 'grid', placeItems: 'center', color: cellFg(c.dials), fontSize: 12.5, fontWeight: 800 }}
                    >
                      <span className="tabular">{c.dials > 0 ? nf(c.dials) : ''}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 12 }}>
            Сколько наборов делают телемаркетологи по часам (МСК) и дням недели · за 3 месяца · всего {nf(grid.totalDials)} наборов по выбранным. Темнее — больше звонят. Выбери одного телемаркетолога — увидишь только его.
          </p>
        </>
      )}
    </div>
  );
}
