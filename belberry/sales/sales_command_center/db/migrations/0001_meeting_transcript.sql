ALTER TABLE "meetings" ADD COLUMN IF NOT EXISTS "transcript_url" text;
--> statement-breakpoint
ALTER TABLE "meetings" ADD COLUMN IF NOT EXISTS "transcript_text" text;
--> statement-breakpoint
ALTER TABLE "meetings" ADD COLUMN IF NOT EXISTS "transcript_ok" boolean;
--> statement-breakpoint
ALTER TABLE "meetings" ADD COLUMN IF NOT EXISTS "analysis_status" text;
