-- Задания КП-движка: сейлс на /kp запрашивает сборку фактуры по сделке,
-- воркер runner/src/kp_worker.py гонит стадии сбора (bitrix → audit → metrika →
-- assemble) и кладёт свод фактов с источниками в kp_data. Сборка деки/сметы —
-- на стороне движка belberry/sales/kp (CLI), серверная сборка — следующий этап.
CREATE TABLE IF NOT EXISTS kp_jobs (
  id serial PRIMARY KEY,
  deal_id integer NOT NULL,
  brand text NOT NULL DEFAULT 'belberry',          -- belberry | acoola
  status text NOT NULL DEFAULT 'pending',          -- pending | collecting | ready | error
  stage text,                                       -- последняя выполненная стадия
  error text,
  kp_data jsonb,                                    -- факты+гипотезы+чек-лист (assemble)
  requested_by integer,                             -- bitrix_id сейлса
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kp_jobs_status_idx ON kp_jobs (status);
CREATE INDEX IF NOT EXISTS kp_jobs_deal_idx ON kp_jobs (deal_id);
