// Доступ к «Аудиту сделок». Пилот (решение заказчика 23.06): на проде видно
// ТОЛЬКО заказчику — строгий allowlist по почте, доступ по роли отключён до
// расширения пилота. role оставлен в сигнатуре для будущего включения РОП.
import type { UserRole } from './session';

export const AUDIT_ALLOWED_EMAILS = ['es@belberry.net'];

export function canSeeAudit(email?: string | null, _role?: UserRole | string | null): boolean {
  return !!email && AUDIT_ALLOWED_EMAILS.includes(email.trim().toLowerCase());
}
