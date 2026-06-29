'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BellRing } from 'lucide-react';

export interface AlertsCounts {
  /** Критичные триггеры по сделкам (Горит + Тишина) — пилюля вкладки «Сделки». */
  dealsCritical: number;
  burningCritical: number;
  silentCount: number;
  /** Просроченные задачи — пилюля вкладки «Задачи». */
  overdueCount: number;
  controlCount: number;
}

/** Пилюля-счётчик на сегменте: красная при >0, иначе скрыта. */
function CountPill({ n, active }: { n: number; active: boolean }) {
  if (n <= 0) return null;
  const style = active
    ? { background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }
    : { background: 'var(--bb-red)', color: '#fff' };
  return (
    <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '1px 7px', marginLeft: 7, ...style }}>{n}</span>
  );
}

/** Hero + сегмент-переключатель вкладок Алертов. Активная вкладка — по pathname. */
export function AlertsHeader({ snapshotDate, counts }: { snapshotDate: string | null; counts: AlertsCounts }) {
  const pathname = usePathname();
  const onTasks = pathname?.startsWith('/alerts/tasks') ?? false;

  const sub = onTasks
    ? `${counts.overdueCount} просроченных задач · ${counts.controlCount} на контроле`
    : `${counts.burningCritical} критичных сделок · ${counts.silentCount} молчат >14 дней`;

  return (
    <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #6a1f2b, #2b2a5e)' }}>
      <div className="bb-hero-row">
        <div style={{ flex: 1 }}>
          <div className="bb-hero-eyebrow">Требуют действий · снимок {snapshotDate ?? '—'}</div>
          <h1 className="bb-hero-title">Алерты</h1>
          <div className="bb-hero-sub">{sub}</div>
        </div>
        <div className="bb-seg" role="tablist">
          <Link href="/alerts/deals" className={onTasks ? '' : 'on'} role="tab" aria-selected={!onTasks}>
            Сделки<CountPill n={counts.dealsCritical} active={!onTasks} />
          </Link>
          <Link href="/alerts/tasks" className={onTasks ? 'on' : ''} role="tab" aria-selected={onTasks}>
            Задачи<CountPill n={counts.overdueCount} active={onTasks} />
          </Link>
        </div>
        <BellRing size={40} color="#fff" style={{ opacity: 0.9 }} />
      </div>
    </div>
  );
}
