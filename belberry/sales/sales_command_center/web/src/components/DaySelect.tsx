'use client';

import { useRouter } from 'next/navigation';

/**
 * Единственное поле выбора дня: календарь/ручной ввод от minDate до сегодня.
 * Выбор сегодняшней даты → режим live (/today без параметра).
 */
export function DaySelect({
  selected,
  minDate,
  maxDate,
}: {
  selected: string | null;
  minDate: string;
  maxDate: string;
}) {
  const router = useRouter();
  return (
    <input
      type="date"
      aria-label="День"
      value={selected ?? maxDate}
      min={minDate}
      max={maxDate}
      onChange={(e) => {
        const v = e.target.value;
        router.push(!v || v === maxDate ? '/today' : `/today?date=${v}`);
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
        colorScheme: 'dark',
      }}
    />
  );
}
