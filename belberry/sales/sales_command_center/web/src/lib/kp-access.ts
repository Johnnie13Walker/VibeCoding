// Фича-гейт страницы «Сборка КП»: пилотный доступ только перечисленным
// пользователям (решение заказчика 11.06). Чистый модуль без БД — импортируется
// и сервером (page/api), и клиентом (Sidebar).
export const KP_ALLOWED_EMAILS = ['es@belberry.net'];

export function canSeeKp(email?: string | null): boolean {
  return !!email && KP_ALLOWED_EMAILS.includes(email.trim().toLowerCase());
}
