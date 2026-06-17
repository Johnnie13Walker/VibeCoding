-- Дата найма сотрудника (из Bitrix DATE_REGISTER) — для расчёта стажа и плана оплат
-- новичков по стажу (1-й мес 0 / 2-й 300к / 3-й+ 500к). Заполняет sync_users_active.
ALTER TABLE users ADD COLUMN IF NOT EXISTS hired_at date;
