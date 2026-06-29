'use client';

import type { AlertManager } from '@/lib/alerts';
import { ManagerPicker } from '@/components/telemarketing/ManagerPicker';

export const PORTAL = 'https://belberrycrm.bitrix24.ru';
export const dealUrl = (id: number) => `${PORTAL}/crm/deal/details/${id}/`;
export const taskUrl = (id: number) => `${PORTAL}/company/personal/user/12/tasks/task/view/${id}/`;

export function fmtDeadline(iso: string | null): string {
  if (!iso) return 'без срока';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(iso));
  } catch { return iso; }
}

export function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(`${iso}T00:00:00+03:00`));
  } catch { return iso; }
}

/** Полная дата ДД.ММ.ГГГГ — для колонки «последний контакт» в «Горит». */
export function fmtDateFull(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Moscow' }).format(new Date(`${iso}T00:00:00+03:00`));
  } catch { return iso; }
}

/** Кал. дней между датой контакта и датой снимка (для «N дн. назад»). */
export function daysAgo(from: string, to: string | null): number | null {
  if (!to) return null;
  const f = new Date(`${from}T00:00:00Z`).getTime();
  const t = new Date(`${to}T00:00:00Z`).getTime();
  if (Number.isNaN(f) || Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((t - f) / 86_400_000));
}

export function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

/** Пикер менеджеров в заголовке секции (справа, рядом с подписью). Скрыт, если
 * менеджеров нет. `small` в .bb-sect-head уже имеет margin-left:auto и уводит вправо
 * себя и пикер — отдельный auto не нужен. */
export function SectionPicker({ managers, selected, onChange }: { managers: AlertManager[]; selected: Set<number>; onChange: (s: Set<number>) => void }) {
  if (managers.length === 0) return null;
  return <ManagerPicker managers={managers} selected={selected} onChange={onChange} allWord="менеджеры" />;
}
