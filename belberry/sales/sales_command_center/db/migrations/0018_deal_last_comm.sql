-- Дата последней коммуникации с клиентом по сделке (звонок/Wazzup, обе стороны).
-- Источник — refresh_runner через transform.last_comm_date: max(последний звонок,
-- последний Wazzup). NULL = контакта с клиентом не было вовсе. Используется блоком
-- «Тишина» на /alerts: открытые сделки кат.10 без коммуникации >14 календарных дней.
ALTER TABLE deals_snapshot ADD COLUMN IF NOT EXISTS last_comm_at date;
