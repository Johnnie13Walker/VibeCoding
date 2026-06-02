-- kp_briefs gets a title column: runner now carries brief/kp title into the row
-- (transform.build_db_rows). Applied live manually on prod earlier — this file
-- makes it reproducible for fresh deploys (psql-apply canon).
ALTER TABLE "kp_briefs" ADD COLUMN IF NOT EXISTS "title" text;
