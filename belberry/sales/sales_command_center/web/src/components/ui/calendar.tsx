'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { DayPicker } from 'react-day-picker';
import { ru } from 'date-fns/locale';
import { cn } from '@/lib/utils';

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  locale = ru,
  weekStartsOn = 1,
  components,
  ...props
}: CalendarProps) {
  return (
    <DayPicker
      className={cn('p-4', className)}
      classNames={{
        root: 'w-full',
        months: 'flex justify-center',
        month: 'w-full space-y-3',
        month_caption: 'relative flex h-9 items-center justify-center',
        caption_label: 'text-sm font-semibold capitalize text-[#1a1f3a]',
        nav: 'absolute inset-x-0 top-0 flex h-9 items-center justify-between',
        button_previous:
          'inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[#e8e4f2] bg-white text-[#5b50d6] transition hover:bg-[#f3effc] disabled:opacity-30',
        button_next:
          'inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[#e8e4f2] bg-white text-[#5b50d6] transition hover:bg-[#f3effc] disabled:opacity-30',
        month_grid: 'w-full table-fixed border-collapse',
        weekdays: '',
        weekday:
          'pb-2 text-center text-[0.7rem] font-semibold uppercase tracking-wide text-[#9aa0b8]',
        week: '',
        day: 'p-0.5 text-center align-middle',
        day_button:
          'mx-auto flex h-9 w-9 items-center justify-center rounded-lg text-sm font-medium text-[#3a3f5c] transition hover:bg-[#f3effc] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent aria-selected:opacity-100',
        selected: 'rounded-lg bg-[#5b50d6] text-white hover:bg-[#4a3fc5]',
        today: 'font-bold text-[#5b50d6]',
        outside: 'text-[#c4c8d6] opacity-60',
        disabled: 'text-[#c4c8d6]',
        hidden: 'invisible',
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation, className: iconClassName, ...iconProps }) =>
          orientation === 'left' ? (
            <ChevronLeft className={cn('h-4 w-4', iconClassName)} {...iconProps} />
          ) : (
            <ChevronRight className={cn('h-4 w-4', iconClassName)} {...iconProps} />
          ),
        ...components,
      }}
      locale={locale}
      showOutsideDays={showOutsideDays}
      weekStartsOn={weekStartsOn}
      {...props}
    />
  );
}
Calendar.displayName = 'Calendar';

export { Calendar };
