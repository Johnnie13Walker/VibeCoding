'use client';

import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import React, { useMemo, useState } from 'react';
import { Calendar } from '@/components/ui/calendar';

interface CalendarViewProps {
  availableDates: string[];
}

export function toReportDateKey(date: Date): string {
  return format(date, 'yyyy-MM-dd');
}

export function CalendarView({ availableDates }: CalendarViewProps) {
  const [month, setMonth] = useState(() =>
    availableDates.length > 0
      ? new Date(`${availableDates[0]}T00:00:00`)
      : new Date(),
  );
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
            'bg-emerald-100 text-emerald-900 font-semibold hover:bg-emerald-200 cursor-pointer rounded-md',
        }}
        month={month}
        onDayClick={openReport}
        onMonthChange={setMonth}
        weekStartsOn={1}
      />
      <p className="mt-3 text-center text-sm text-slate-500">
        Выберите день — отчёт откроется в новой вкладке.
      </p>
    </div>
  );
}
