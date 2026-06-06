CREATE TABLE "deals_snapshot" (
	"id" serial PRIMARY KEY NOT NULL,
	"report_date" date NOT NULL,
	"deal_id" integer NOT NULL,
	"category_id" integer,
	"stage" text NOT NULL,
	"opportunity" numeric(14, 2),
	"manager_id" integer,
	"stuck_days" integer,
	"stage_entered" date,
	"title" text,
	"company_id" integer,
	CONSTRAINT "deals_snapshot_report_date_deal_id_unique" UNIQUE("report_date","deal_id")
);
--> statement-breakpoint
CREATE TABLE "kp_briefs" (
	"id" serial PRIMARY KEY NOT NULL,
	"report_date" date NOT NULL,
	"item_id" integer NOT NULL,
	"deal_id" integer,
	"item_type" text NOT NULL,
	"stage" text,
	"manager_id" integer,
	"amount" numeric(14, 2),
	CONSTRAINT "kp_briefs_report_date_item_id_item_type_unique" UNIQUE("report_date","item_id","item_type")
);
--> statement-breakpoint
CREATE TABLE "login_codes" (
	"id" serial PRIMARY KEY NOT NULL,
	"email" text NOT NULL,
	"code" text NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"used" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "manager_activity" (
	"id" serial PRIMARY KEY NOT NULL,
	"report_date" date NOT NULL,
	"manager_id" integer NOT NULL,
	"calls_total" integer DEFAULT 0,
	"calls_answered" integer DEFAULT 0,
	"calls_120s_plus" integer DEFAULT 0,
	"dials_total" integer DEFAULT 0,
	"meetings_set" integer DEFAULT 0,
	"meetings_held" integer DEFAULT 0,
	"briefs_created" integer DEFAULT 0,
	"kp_sent" integer DEFAULT 0,
	CONSTRAINT "manager_activity_report_date_manager_id_unique" UNIQUE("report_date","manager_id")
);
--> statement-breakpoint
CREATE TABLE "meetings" (
	"id" serial PRIMARY KEY NOT NULL,
	"report_date" date NOT NULL,
	"meeting_id" integer NOT NULL,
	"deal_id" integer,
	"meeting_type" text,
	"status" text,
	"manager_id" integer,
	"scheduled_at" timestamp with time zone,
	"analysis_json" jsonb,
	CONSTRAINT "meetings_report_date_meeting_id_unique" UNIQUE("report_date","meeting_id")
);
--> statement-breakpoint
CREATE TABLE "plans" (
	"id" serial PRIMARY KEY NOT NULL,
	"period" text NOT NULL,
	"manager_id" integer,
	"metric" text NOT NULL,
	"target" numeric(14, 2) NOT NULL,
	CONSTRAINT "plans_period_manager_id_metric_unique" UNIQUE("period","manager_id","metric")
);
--> statement-breakpoint
CREATE TABLE "reports" (
	"report_date" date PRIMARY KEY NOT NULL,
	"status" text DEFAULT 'pending' NOT NULL,
	"html" text,
	"summary_json" jsonb,
	"generated_at" timestamp with time zone,
	"error_msg" text,
	"retry_count" smallint DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE "sessions" (
	"token" text PRIMARY KEY NOT NULL,
	"bitrix_id" integer,
	"expires_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "users" (
	"bitrix_id" integer PRIMARY KEY NOT NULL,
	"email" text NOT NULL,
	"name" text NOT NULL,
	"role" text DEFAULT 'manager' NOT NULL,
	"dept" text,
	"is_active" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now(),
	"updated_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "users_email_unique" UNIQUE("email")
);
--> statement-breakpoint
ALTER TABLE "deals_snapshot" ADD CONSTRAINT "deals_snapshot_report_date_reports_report_date_fk" FOREIGN KEY ("report_date") REFERENCES "public"."reports"("report_date") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "kp_briefs" ADD CONSTRAINT "kp_briefs_report_date_reports_report_date_fk" FOREIGN KEY ("report_date") REFERENCES "public"."reports"("report_date") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "manager_activity" ADD CONSTRAINT "manager_activity_report_date_reports_report_date_fk" FOREIGN KEY ("report_date") REFERENCES "public"."reports"("report_date") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "meetings" ADD CONSTRAINT "meetings_report_date_reports_report_date_fk" FOREIGN KEY ("report_date") REFERENCES "public"."reports"("report_date") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_bitrix_id_users_bitrix_id_fk" FOREIGN KEY ("bitrix_id") REFERENCES "public"."users"("bitrix_id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "deals_snapshot_report_date_manager_id_idx" ON "deals_snapshot" USING btree ("report_date","manager_id");--> statement-breakpoint
CREATE INDEX "deals_snapshot_report_date_category_id_stage_idx" ON "deals_snapshot" USING btree ("report_date","category_id","stage");--> statement-breakpoint
CREATE INDEX "login_codes_email_used_expires_at_idx" ON "login_codes" USING btree ("email","used","expires_at");