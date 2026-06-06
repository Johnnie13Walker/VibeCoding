-- Wazzup-чаты «Сегодня» (отдельный часовой проход, тяжёлый per-deal скан).
-- Хранится отдельно от live_snapshot, чтобы лёгкий 20-мин live не затирал.
CREATE TABLE IF NOT EXISTS "live_chats" (
	"id" smallint PRIMARY KEY DEFAULT 1,
	"updated_at" timestamp with time zone NOT NULL DEFAULT now(),
	"report_date" date,
	"payload" jsonb NOT NULL,
	CONSTRAINT "live_chats_singleton" CHECK ("id" = 1)
);
