-- Снимок «Сегодня» (live): одна строка, обновляется частым cron (без Wazzup/LLM).
CREATE TABLE IF NOT EXISTS "live_snapshot" (
	"id" smallint PRIMARY KEY DEFAULT 1,
	"updated_at" timestamp with time zone NOT NULL DEFAULT now(),
	"report_date" date,
	"payload" jsonb NOT NULL,
	CONSTRAINT "live_snapshot_singleton" CHECK ("id" = 1)
);
