-- Фактические приходы (оплаты) из финансовой таблицы «Приходы 2026», вкладка «Продажи».
-- Источник правды по деньгам (не Bitrix-won). Зеркало вкладки: sync_payments.py
-- делает полную перезапись (DELETE+INSERT). «Оплата» на дашборде = КД без НДС
-- (kd_no_vat), Отдел=Продажи, по Месяцу оплаты (pay_month) + Году (pay_year).
CREATE TABLE IF NOT EXISTS payments (
  id serial PRIMARY KEY,
  project text,
  source text,
  dept text,
  manager text,
  service text,
  kd_with_vat numeric(14, 2),
  kd_no_vat numeric(14, 2),
  dd_with_vat numeric(14, 2),
  dd_no_vat numeric(14, 2),
  pay_date text,
  pay_form text,
  counterparty text,
  brand text,
  pay_month smallint,
  pay_year integer,
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payments_year_month_dept_idx ON payments (pay_year, pay_month, dept);
