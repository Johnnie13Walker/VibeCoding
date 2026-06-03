// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { format, subMonths } from 'date-fns';
import { ru } from 'date-fns/locale';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CalendarView } from '../CalendarView';

function visibleDate(day: number) {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), day);
}

function dayButton(day: number) {
  return screen.getAllByRole('button', {
    name: new RegExp(`\\b${day}\\b`),
  })[0];
}

describe('CalendarView', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('enables and highlights available days while disabling unavailable days', () => {
    const available = format(visibleDate(15), 'yyyy-MM-dd');

    render(<CalendarView availableDates={[available]} />);

    const availableDay = dayButton(15);
    const unavailableDay = dayButton(16);

    expect(availableDay).not.toBeDisabled();
    expect(availableDay.closest('td')?.className).toContain('bg-emerald-100');
    expect(unavailableDay).toBeDisabled();
  });

  it('opens available report in a new noopener tab', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    const available = format(visibleDate(15), 'yyyy-MM-dd');

    render(<CalendarView availableDates={[available]} />);
    fireEvent.click(dayButton(15));

    expect(open).toHaveBeenCalledWith(`/day/${available}`, '_blank', 'noopener');
  });

  it('navigates to the previous month from the calendar controls', () => {
    const currentMonthReport = format(visibleDate(15), 'yyyy-MM-dd');
    const previousMonth = subMonths(visibleDate(15), 1);
    const previousMonthReport = format(previousMonth, 'yyyy-MM-dd');

    render(<CalendarView availableDates={[currentMonthReport, previousMonthReport]} />);
    fireEvent.click(screen.getByLabelText('Go to the Previous Month'));

    expect(screen.getByText(format(previousMonth, 'LLLL yyyy', { locale: ru }))).toBeInTheDocument();
  });
});
