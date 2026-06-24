-- Петля отслеживания возврата (#3): зафиксировать момент/стадию возврата и результат
-- проверки через N дней — сработал ли возврат (двинулась ли сделка).
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS returned_at TIMESTAMPTZ;
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS return_stage TEXT;       -- стадия, выставленная при возврате
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS followup_status TEXT;    -- progressed | stalled | in_progress
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS followup_note TEXT;
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS followup_at TIMESTAMPTZ; -- когда проверили
