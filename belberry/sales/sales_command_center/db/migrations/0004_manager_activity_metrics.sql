-- manager_activity получает talk_seconds (часы разговоров) и deals_created_count
-- (новые сделки на менеджера). runner пишет эти поля (transform.build_db_rows) →
-- без колонок daily_runner падает «column talk_seconds does not exist». psql-канон.
ALTER TABLE "manager_activity" ADD COLUMN IF NOT EXISTS "talk_seconds" integer DEFAULT 0;
ALTER TABLE "manager_activity" ADD COLUMN IF NOT EXISTS "deals_created_count" integer DEFAULT 0;
