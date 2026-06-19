-- Причина отвала (UF_CRM_1771495464) в когорте — чтобы исключать СПАМ (8588) из
-- воронки Продажи [10] (правило аудита воронки 2026). Заполняется sync_funnel_cohort.
ALTER TABLE funnel_cohort ADD COLUMN IF NOT EXISTS reason_id integer;
