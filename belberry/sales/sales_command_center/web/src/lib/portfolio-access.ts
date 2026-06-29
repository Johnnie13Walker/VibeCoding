import type { UserRole } from './session';

// «Портфолио» открыто ВСЕМ авторизованным сотрудникам командного центра
// (с 29.06 — раньше был пилот только для владельца). Сигнатура сохранена,
// чтобы при необходимости снова сузить доступ в одном месте.
export function canSeePortfolio(
  _email?: string | null,
  _role?: UserRole | string | null,
  _bitrixId?: number | null,
): boolean {
  return true;
}
