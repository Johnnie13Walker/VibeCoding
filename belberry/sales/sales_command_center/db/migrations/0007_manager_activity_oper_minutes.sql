-- Модель «Опер» = реальные рабочие минуты. Формула берёт звонки 60с+ (как
-- «дозвон» по 5 мин) и письма (по 5 мин). transform.build_db_rows теперь пишет
-- эти поля в manager_activity → без колонок daily_runner упадёт
-- «column calls_60s_plus does not exist». psql-канон.
ALTER TABLE "manager_activity" ADD COLUMN IF NOT EXISTS "calls_60s_plus" integer DEFAULT 0;
ALTER TABLE "manager_activity" ADD COLUMN IF NOT EXISTS "emails_sent" integer DEFAULT 0;
