'use client';

import { useRouter } from 'next/navigation';

function fmt(d: string): string {
  const [y, m, dd] = d.split('-');
  if (!y || !m || !dd) return d;
  return `${dd}.${m}.${y}`;
}

export function DaySelect({ dates, selected }: { dates: string[]; selected: string | null }) {
  const router = useRouter();
  return (
    <select
      aria-label="Выбрать день"
      value={selected ?? ''}
      onChange={(e) => {
        const v = e.target.value;
        router.push(v ? `/today?date=${v}` : '/today');
      }}
      style={{
        appearance: 'none',
        background: 'rgba(255,255,255,0.16)',
        color: '#fff',
        border: '1px solid rgba(255,255,255,0.3)',
        borderRadius: 10,
        padding: '8px 14px',
        fontSize: 14,
        fontWeight: 600,
        cursor: 'pointer',
      }}
    >
      <option value="" style={{ color: '#111' }}>● Сегодня (live)</option>
      {dates.map((d) => (
        <option key={d} value={d} style={{ color: '#111' }}>
          {fmt(d)}
        </option>
      ))}
    </select>
  );
}
