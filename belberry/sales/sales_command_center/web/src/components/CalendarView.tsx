'use client';

import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import React, { useMemo } from 'react';
import { Calendar } from '@/components/ui/calendar';

interface CalendarViewProps {
  availableDates: string[];
}

export function toReportDateKey(date: Date): string {
  return format(date, 'yyyy-MM-dd');
}

export function CalendarView({ availableDates }: CalendarViewProps) {
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

    window.open(`/day/${key}`, '_blank', 'noopener');
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <Calendar
        className="rounded-lg border border-slate-200 bg-white shadow-sm"
        disabled={(date) => !availableSet.has(toReportDateKey(date))}
        locale={ru}
        mode="single"
        modifiers={{
          available: (date) => availableSet.has(toReportDateKey(date)),
        }}
        modifiersClassNames={{
          available:
            'bg-[#ece9f9] text-[#4a3fc5] font-semibold hover:bg-[#ddd6f7] cursor-pointer rounded-md',
        }}
        defaultMonth={initialMonth}
        onDayClick={openReport}
        weekStartsOn={1}
      />
      <p className="mt-3 text-center text-sm text-slate-500">
        Выберите день — отчёт откроется в новой вкладке.
      </p>
    </div>
  );
}
