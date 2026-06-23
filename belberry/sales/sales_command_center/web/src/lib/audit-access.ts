// Доступ к «Аудиту сделок»: только руководитель/РОП + явный allowlist почт
// (решение заказчика 23.06). Чистый модуль без БД — импортируется сервером
// (page/api) и клиентом (Sidebar).
import type { UserRole } from './session';

export const AUDIT_ALLOWED_EMAILS = ['es@belberry.net'];

export function canSeeAudit(email?: string | null, role?: UserRole | string | null): boolean {
  if (role === 'director' || role === 'rop') return true;
  return !!email && AUDIT_ALLOWED_EMAILS.includes(email.trim().toLowerCase());
}
