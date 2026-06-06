'use client';

import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import React, { useMemo } from 'react';
import { Calendar } from '@/components/ui/calendar';

interface CalendarViewProps {
  availableDates: string[];
  /** Если задан — день открывается внутри платформы (без новой вкладки). */
  onSelect?: (dateKey: string) => void;
}

export function toReportDateKey(date: Date): string {
  return format(date, 'yyyy-MM-dd');
}

export function CalendarView({ availableDates, onSelect }: CalendarViewProps) {
  // Открываем на месяце самого свежего отчёта (availableDates отсортированы desc),
  // но НЕ позже текущего месяца — иначе тестовая запись с будущей датой увела бы
  // календарь в пустое будущее. Месяц неконтролируемый (defaultMonth) — листание
  // назад/вперёд rdp ведёт сам, без риска зависнуть на контролируемом state.
  const initialMonth = useMemo(() => {
    const now = new Date();
    if (availableDates.length === 0) {
      return now;
    }
    const latest = new Date(`${availableDates[0]}T00:00:00`);
    return latest > now ? now : latest;
  }, [availableDates]);
  const availableSet = useMemo(() => new Set(availableDates), [availableDates]);

  function openReport(date: Date) {
    const key = toReportDateKey(date);

    if (!availableSet.has(key)) {
      return;
    }

    if (onSelect) {
      onSelect(key);
      return;
    }

    window.open(`/day/${key}`, '_blank', 'noopener');
  }

  return (
    <div className="w-full max-w-sm">
      <Calendar
        className="rounded-2xl border border-[#e8e4f2] bg-white shadow-sm"
        disabled={(date) => !availableSet.has(toReportDateKey(date))}
        locale={ru}
        mode="single"
        modifiers={{
          available: (date) => availableSet.has(toReportDateKey(date)),
        }}
        modifiersClassNames={{
          // Стилизуем саму кнопку дня (она круглая) — мягкая фиолетовая «таблетка»
          // как в Apple Calendar; подсветка попадает на круг, а не на прямоугольную ячейку.
          available:
            'cursor-pointer [&>button]:bg-[#ece9f9] [&>button]:font-semibold [&>button]:text-[#5b50d6] [&>button:hover]:bg-[#e0dbf7]',
        }}
        defaultMonth={initialMonth}
        onDayClick={openReport}
        weekStartsOn={1}
      />
      <p className="mt-3 text-sm text-[#6b6f88]">
        {onSelect ? 'Выберите день — отчёт откроется здесь.' : 'Выберите день — отчёт откроется в новой вкладке.'}
      </p>
    </div>
  );
}
