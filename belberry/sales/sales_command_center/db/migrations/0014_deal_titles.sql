-- Справочник названий сделок (TITLE = домен у Belberry) для встреч. deals_snapshot
-- хранит только ОТКРЫТЫЕ сделки → у закрытых/выигранных встреч название не
-- резолвилось и показывалось «Сделка #id». Эта таблица покрывает ВСЕ сделки,
-- на которые есть встречи (включая закрытые). Наполняется sync_deal_titles.py
-- (разово + в дневном прогоне). Upsert по deal_id.
CREATE TABLE IF NOT EXISTS deal_titles (
  deal_id integer PRIMARY KEY,
  title text,
  updated_at timestamptz DEFAULT now()
);
