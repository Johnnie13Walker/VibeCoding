'use client';

import { useMemo, useState } from 'react';
import { aggregateTmFunnel, type TmFunnel50 } from '@/lib/telemarketing-shared';
import { ManagerPicker } from './ManagerPicker';

const nf = (n: number) => new Intl.NumberFormat('ru-RU').format(n);

export function TmFunnel50View({ data }: { data: TmFunnel50 }) {
  const allIds = useMemo(() => data.selectableManagers.map((m) => m.managerId), [data.selectableManagers]);
  const [selected, setSelected] = useState<Set<number>>(() => new Set(allIds));

  const stages = useMemo(
    () => aggregateTmFunnel(data.perManager, selected, data.stages),
    [data.perManager, data.stages, selected],
  );

  const max = Math.max(...stages.map((s) => s.count), 1);
  const fill = (kind: string) =>
    kind === 'win' ? 'linear-gradient(90deg,#3a9c63,#2c7a4a)'
      : kind === 'lose' ? 'linear-gradient(90deg,#e0606b,#d4202e)'
        : 'linear-gradient(90deg,var(--bb-violet),var(--bb-indigo))';
  // Закрытые стадии показываем только при наличии данных.
  const shown = stages.filter((s) => s.kind === 'open' || s.count > 0);
  const empty = stages.every((s) => s.count === 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14, marginTop: -4 }}>
        <ManagerPicker managers={data.selectableManagers} selected={selected} onChange={setSelected} allWord="владельцы" />
      </div>
      {empty ? (
        <p style={{ color: 'var(--bb-muted)' }}>Нет открытых сделок cat50 по выбранным владельцам.</p>
      ) : (
        <div className="bb-funnel">
          {shown.map((s) => (
            <div className="bb-fbar" key={s.stage}>
              <span className="bb-fbar-name">{s.label}</span>
              <div className="bb-fbar-track">
                <div className="bb-fbar-fill" style={{ width: `${Math.max(8, (s.count / max) * 100)}%`, background: fill(s.kind) }}>{nf(s.count)}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Снимок открытых сделок cat50 по владельцам (ТМ и МП). Закрытые (Успех/Отвал) — со сбором потока в раннере.
      </p>
    </div>
  );
}
