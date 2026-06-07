-- Событийный слой отвалов ТМ-воронки [50]: одна строка на закрытую сделку
-- (C50:APOLOGY = отвал, C50:LOSE = отложено) с причиной (UF_CRM_1771324790),
-- тем кто закрыл (modified_by) и владельцем (assigned_by). Метрики причин отвала,
-- сжигания базы и Отвал/Отлож считаются SQL-запросом по этой таблице —
-- накопленно и за период (по rejected_at). Наполняется разово (бэкафилл) +
-- ежедневно (закрытые за день). Upsert по deal_id.
CREATE TABLE IF NOT EXISTS deal_rejections (
  deal_id integer PRIMARY KEY,
  category_id integer,
  stage_id text NOT NULL,
  reason_id integer,
  modified_by integer,
  assigned_by integer,
  rejected_at timestamptz,
  title text,
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS deal_rejections_modified_by_reason_idx
  ON deal_rejections (modified_by, reason_id);
CREATE INDEX IF NOT EXISTS deal_rejections_stage_rejected_idx
  ON deal_rejections (stage_id, rejected_at);
