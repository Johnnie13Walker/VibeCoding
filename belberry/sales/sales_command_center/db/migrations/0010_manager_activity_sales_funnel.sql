-- Воронка вход→оплата (перенос метрик старого дашборда ОП).
-- deals_cold_count / deals_incoming_count — разрез созданных сделок по происхождению
--   (ТМ-воронка CAT 50 = холод; Продажи CAT 10 = по источнику: outbound = холод, иначе вход).
-- deals_won_count / deals_won_amount — оплаты: переход сделки в C10:WON за день, шт и сумма ₽.
-- DEFAULT 0: исторические дни до миграции считаем «нулём», а не NULL, чтобы суммы/средний чек
--   по периоду не ломались на NULL.
ALTER TABLE manager_activity ADD COLUMN IF NOT EXISTS deals_cold_count integer DEFAULT 0;
ALTER TABLE manager_activity ADD COLUMN IF NOT EXISTS deals_incoming_count integer DEFAULT 0;
ALTER TABLE manager_activity ADD COLUMN IF NOT EXISTS deals_won_count integer DEFAULT 0;
ALTER TABLE manager_activity ADD COLUMN IF NOT EXISTS deals_won_amount numeric(14,2) DEFAULT 0;
