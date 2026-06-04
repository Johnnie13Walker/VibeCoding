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
        month: 'relative w-full space-y-3',
        month_caption: 'relative flex h-10 items-center justify-center',
        caption_label: 'text-[0.95rem] font-semibold capitalize text-[#1d1d1f]',
        nav: 'absolute inset-x-0 top-0 z-10 flex h-10 items-center justify-between px-1',
        button_previous:
          'inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#e8e4f2] bg-white text-[#5b50d6] shadow-sm transition hover:bg-[#f0eefb] hover:border-[#d6cffb] disabled:opacity-30 disabled:hover:bg-white',
        button_next:
          'inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#e8e4f2] bg-white text-[#5b50d6] shadow-sm transition hover:bg-[#f0eefb] hover:border-[#d6cffb] disabled:opacity-30 disabled:hover:bg-white',
        month_grid: 'w-full table-fixed border-collapse',
        weekdays: '',
        weekday:
          'pb-2 text-center text-[0.7rem] font-medium uppercase tracking-wider text-[#86868b]',
        week: '',
        day: 'p-0.5 text-center align-middle',
        day_button:
          'mx-auto flex h-9 w-9 items-center justify-center rounded-full text-sm font-medium text-[#1d1d1f] transition hover:bg-[#f0f0f3] disabled:cursor-not-allowed disabled:text-[#c7c7cc] disabled:hover:bg-transparent aria-selected:opacity-100',
        selected: 'rounded-full bg-[#5b50d6] text-white hover:bg-[#4a3fc5]',
        today: 'font-bold text-[#5b50d6]',
        outside: 'text-[#c7c7cc] opacity-60',
        disabled: 'text-[#c7c7cc]',
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
