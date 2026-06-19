-- Выигрыши Продажи [10] (событийный слой) — надёжный источник «выиграла ли сделка
-- + сумма по deal_id». Зеркало deal_rejections, но по переходам в C10:WON из
-- stagehistory (won-сделка уходит из снимка → текущую стадию не поймать). Нужен для
-- окупаемости ТМ (встречи → деньги) и любых downstream-метрик «дошло до оплаты».
-- Заполняет sync_wins.py (один прогон с начала года = бэкафилл; cron — свежесть).
CREATE TABLE IF NOT EXISTS deal_wins (
  deal_id integer PRIMARY KEY,
  won_date date,                       -- дата перехода в C10:WON (CREATED_TIME)
  opportunity numeric(14, 2),          -- сумма сделки (OPPORTUNITY ≡ Σ productrow)
  owner_id integer,                    -- ASSIGNED_BY_ID (ответственный/продавец)
  owner_name text,
  owner_dept text,
  owner_active boolean,
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS deal_wins_won_date_idx ON deal_wins (won_date);
