-- Аудит сделок: задания страницы /audit. Веб создаёт pending, воркер аудита
-- (audit_worker.py) прогоняет audit_engine и пишет результат + шанс возврата.
CREATE TABLE IF NOT EXISTS deal_audits (
  id SERIAL PRIMARY KEY,
  deal_id INTEGER NOT NULL,
  title TEXT,
  company TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending|collecting|ready|error
  stage TEXT,
  error TEXT,
  score INTEGER,                            -- шанс возврата 0..100
  band TEXT,                                -- low|mid|hi
  expected_value INTEGER,                   -- шанс × сумма сделки, ₽
  result JSONB,                             -- полный результат audit_engine.audit_deal
  requested_by INTEGER,                     -- bitrix user id инициатора
  returned_to_work BOOLEAN NOT NULL DEFAULT false,
  task_id INTEGER,                          -- id поставленной задачи при возврате
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS deal_audits_status_idx ON deal_audits(status);
CREATE INDEX IF NOT EXISTS deal_audits_deal_idx ON deal_audits(deal_id);
