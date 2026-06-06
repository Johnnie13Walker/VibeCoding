-- Событийный слой встреч: создатель встречи (ТМ-телемаркетолог) в таблице meetings.
-- Делает meetings источником событий для метрик ТМ: «встречу назначил ТМ и она
-- состоялась» (status=DT1048_24:SUCCESS, created_by ∈ ТМ) считается SQL-запросом —
-- без агрегат-колонок и бэкафилла на каждую новую метрику встреч.
-- NULL = строка из времени до этой миграции (наполнится бэкафиллом).
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS created_by integer;
CREATE INDEX IF NOT EXISTS meetings_created_by_status_idx ON meetings (created_by, status, report_date);
