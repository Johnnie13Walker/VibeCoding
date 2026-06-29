import type { UserRole } from './session';

// Раздел «Портфолио» пока виден только владельцу (Щемелёв). Открыть шире —
// расширить условие здесь (одно место). Гейтим и пункт меню, и саму страницу.
const OWNER_EMAIL = 'es@belberry.net';
const OWNER_BITRIX_ID = 12;

export function canSeePortfolio(
  email?: string | null,
  role?: UserRole | string | null,
  bitrixId?: number | null,
): boolean {
  return role === 'director' || (email ?? '').trim().toLowerCase() === OWNER_EMAIL || bitrixId === OWNER_BITRIX_ID;
}
