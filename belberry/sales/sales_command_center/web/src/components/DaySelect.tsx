'use client';

import { useRouter } from 'next/navigation';

function fmt(d: string): string {
  const [y, m, dd] = d.split('-');
  if (!y || !m || !dd) return d;
  return `${dd}.${m}.${y}`;
}

const ctrlStyle: React.CSSProperties = {
  appearance: 'none',
  background: 'rgba(255,255,255,0.16)',
  color: '#fff',
  border: '1px solid rgba(255,255,255,0.3)',
  borderRadius: 10,
  padding: '8px 12px',
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  colorScheme: 'dark',
};

export function DaySelect({
  dates,
  selected,
  maxDate,
}: {
  dates: string[];
  selected: string | null;
  maxDate: string;
}) {
  const router = useRouter();
  const go = (v: string) => router.push(v ? `/today?date=${v}` : '/today');

  // в списке всегда есть выбранная дата (даже если её нет среди готовых отчётов)
  const options = selected && !dates.includes(selected) ? [selected, ...dates] : dates;

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
      <select
        aria-label="Выбрать день из готовых отчётов"
        value={selected ?? ''}
        onChange={(e) => go(e.target.value)}
        style={ctrlStyle}
      >
        <option value="" style={{ color: '#111' }}>● Сегодня (live)</option>
        {options.map((d) => (
          <option key={d} value={d} style={{ color: '#111' }}>
            {fmt(d)}
          </option>
        ))}
      </select>

      <input
        type="date"
        aria-label="Ввести дату вручную"
        value={selected ?? ''}
        max={maxDate}
        onChange={(e) => go(e.target.value)}
        style={{ ...ctrlStyle, cursor: 'text' }}
      />

      {selected ? (
        <button type="button" onClick={() => go('')} style={{ ...ctrlStyle, fontWeight: 700 }}>
          ● Сегодня
        </button>
      ) : null}
    </div>
  );
}
