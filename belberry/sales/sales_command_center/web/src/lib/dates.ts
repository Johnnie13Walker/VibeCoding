import { format, isValid, parseISO } from 'date-fns';
import { z } from 'zod';

export const dateParamSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export function parseReportDate(raw: string): string | null {
  const parsed = dateParamSchema.safeParse(raw);

  if (!parsed.success) {
    return null;
  }

  const date = parseISO(parsed.data);

  if (!isValid(date) || format(date, 'yyyy-MM-dd') !== parsed.data) {
    return null;
  }

  return parsed.data;
}

export function isReportAvailable(date: string, available: Set<string> | string[]): boolean {
  const availableSet = Array.isArray(available) ? new Set(available) : available;

  return availableSet.has(date);
}
