-- Превентив (#5): живые сделки с процессными красными флагами (КП мимо системы,
-- защита не проведена, стрельба брифами, handover…) — снимок для блока «Риск процесса» в Алертах.
CREATE TABLE IF NOT EXISTS deal_risk_flags (
  deal_id     INTEGER PRIMARY KEY,
  title       TEXT,
  stage_label TEXT,
  manager_id  INTEGER,
  flags       JSONB NOT NULL DEFAULT '[]',
  severity    TEXT NOT NULL DEFAULT 'warning',  -- critical | warning
  checked_at  TIMESTAMPTZ DEFAULT now()
);
