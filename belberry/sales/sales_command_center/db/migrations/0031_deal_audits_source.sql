-- Источник аудита: manual (запущен человеком со страницы) | auto (радар застрявших сделок).
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';
