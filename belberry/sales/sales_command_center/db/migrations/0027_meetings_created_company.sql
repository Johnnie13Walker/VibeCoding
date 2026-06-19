-- Паритет архива /today с «сегодня»: храним назначенные встречи (созданные в день)
-- и годовую выручку компании для ТМ-брифингов. created_at = когда встреча создана
-- (для «Встречи назначены» за прошлые даты: setToday = created_at в день отчёта);
-- company_revenue = годовая выручка компании сделки (раньше была только в live).
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS created_at timestamptz;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS company_revenue numeric(14, 2);
