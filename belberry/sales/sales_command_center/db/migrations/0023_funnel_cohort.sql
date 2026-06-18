-- Интейк-когорта воронки Продажи [10]: одна строка на сделку, созданную с начала
-- года, с самой дальней достигнутой стадией (по stagehistory + текущая). Позволяет
-- честно считать «из созданных за месяц сколько ДОШЛО до этапа X» (одни и те же
-- сделки), а не смешивать события. Заполняется src/sync_funnel_cohort.py (upsert
-- by deal_id), отдельно от дневного пайплайна.
CREATE TABLE IF NOT EXISTS funnel_cohort (
  deal_id integer PRIMARY KEY,
  category_id integer,
  cohort_date date,           -- дата создания сделки (определяет месяц когорты)
  manager_id integer,         -- ASSIGNED_BY_ID
  current_stage text,         -- текущая стадия Bitrix
  furthest_stage text,        -- самая дальняя достигнутая стадия пути
  furthest_order integer,     -- её порядок (0 — вне пути)
  is_won boolean,             -- дошла до C10:WON
  is_lost boolean,            -- сейчас в ОТВАЛ/ОТЛОЖЕНО (C10:LOSE/C10:1)
  opportunity numeric(14, 2),
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS funnel_cohort_cohort_date_manager_idx
  ON funnel_cohort (cohort_date, manager_id);
