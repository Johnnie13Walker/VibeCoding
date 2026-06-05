-- Идемпотентность автозадач из разбора встреч + витрина статусов для дашборда.
-- Одна строка = одна созданная задача Bitrix по конкретному шагу встречи.
-- UNIQUE (meeting_id, step_key) не даёт продублировать задачу при повторном прогоне/--force.
CREATE TABLE IF NOT EXISTS meeting_tasks (
  id            serial PRIMARY KEY,
  report_date   date NOT NULL,
  meeting_id    integer NOT NULL,
  deal_id       integer,
  step_key      text NOT NULL,            -- нормализованный ключ шага (см. tasks.step_key)
  task_id       integer NOT NULL,         -- id задачи в Bitrix24
  responsible_id integer,
  title         text,
  deadline      timestamptz,
  status        integer,                  -- статус задачи Bitrix (синкается live-проходом)
  closed        boolean NOT NULL DEFAULT false,  -- принята/завершена → скрыть из дашборда
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz,
  UNIQUE (meeting_id, step_key)
);

CREATE INDEX IF NOT EXISTS meeting_tasks_open_idx ON meeting_tasks (closed, deadline);
