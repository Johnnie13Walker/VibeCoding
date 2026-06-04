import {
  boolean,
  date,
  index,
  integer,
  jsonb,
  numeric,
  pgTable,
  serial,
  smallint,
  text,
  timestamp,
  unique,
} from 'drizzle-orm/pg-core';

export const users = pgTable('users', {
  bitrixId: integer('bitrix_id').primaryKey(),
  email: text('email').notNull().unique(),
  name: text('name').notNull(),
  role: text('role').notNull().default('manager'),
  dept: text('dept'),
  isActive: boolean('is_active').notNull().default(true),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
});

export const loginCodes = pgTable(
  'login_codes',
  {
    id: serial('id').primaryKey(),
    email: text('email').notNull(),
    // stores SHA-256 hash of the OTP, never plaintext (PITFALLS Pitfall 11)
    code: text('code').notNull(),
    expiresAt: timestamp('expires_at', { withTimezone: true }).notNull(),
    used: boolean('used').notNull().default(false),
    attempts: integer('attempts').notNull().default(0),
    createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [
    index('login_codes_email_used_expires_at_idx').on(
      table.email,
      table.used,
      table.expiresAt,
    ),
  ],
);

export const sessions = pgTable('sessions', {
  token: text('token').primaryKey(),
  bitrixId: integer('bitrix_id').references(() => users.bitrixId),
  expiresAt: timestamp('expires_at', { withTimezone: true }).notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const liveSnapshot = pgTable('live_snapshot', {
  id: smallint('id').primaryKey(),
  updatedAt: timestamp('updated_at', { withTimezone: true }),
  reportDate: date('report_date'),
  payload: jsonb('payload'),
});

export const reports = pgTable('reports', {
  reportDate: date('report_date').primaryKey(),
  status: text('status').notNull().default('pending'),
  html: text('html'),
  summaryJson: jsonb('summary_json'),
  generatedAt: timestamp('generated_at', { withTimezone: true }),
  errorMsg: text('error_msg'),
  retryCount: smallint('retry_count').notNull().default(0),
});

export const dealsSnapshot = pgTable(
  'deals_snapshot',
  {
    id: serial('id').primaryKey(),
    reportDate: date('report_date')
      .notNull()
      .references(() => reports.reportDate),
    dealId: integer('deal_id').notNull(),
    categoryId: integer('category_id'),
    stage: text('stage').notNull(),
    opportunity: numeric('opportunity', { precision: 14, scale: 2 }),
    managerId: integer('manager_id'),
    stuckDays: integer('stuck_days'),
    stageEntered: date('stage_entered'),
    title: text('title'),
    companyId: integer('company_id'),
  },
  (table) => [
    unique('deals_snapshot_report_date_deal_id_unique').on(
      table.reportDate,
      table.dealId,
    ),
    index('deals_snapshot_report_date_manager_id_idx').on(
      table.reportDate,
      table.managerId,
    ),
    index('deals_snapshot_report_date_category_id_stage_idx').on(
      table.reportDate,
      table.categoryId,
      table.stage,
    ),
  ],
);

export const meetings = pgTable(
  'meetings',
  {
    id: serial('id').primaryKey(),
    reportDate: date('report_date')
      .notNull()
      .references(() => reports.reportDate),
    meetingId: integer('meeting_id').notNull(),
    dealId: integer('deal_id'),
    meetingType: text('meeting_type'),
    status: text('status'),
    managerId: integer('manager_id'),
    scheduledAt: timestamp('scheduled_at', { withTimezone: true }),
    analysisJson: jsonb('analysis_json'),
    transcriptUrl: text('transcript_url'),
    transcriptText: text('transcript_text'),
    transcriptOk: boolean('transcript_ok'),
    analysisStatus: text('analysis_status'),
  },
  (table) => [
    unique('meetings_report_date_meeting_id_unique').on(
      table.reportDate,
      table.meetingId,
    ),
  ],
);

export const managerActivity = pgTable(
  'manager_activity',
  {
    id: serial('id').primaryKey(),
    reportDate: date('report_date')
      .notNull()
      .references(() => reports.reportDate),
    managerId: integer('manager_id').notNull(),
    callsTotal: integer('calls_total').default(0),
    callsAnswered: integer('calls_answered').default(0),
    calls120sPlus: integer('calls_120s_plus').default(0),
    dialsTotal: integer('dials_total').default(0),
    meetingsSet: integer('meetings_set').default(0),
    meetingsHeld: integer('meetings_held').default(0),
    briefsCreated: integer('briefs_created').default(0),
    kpSent: integer('kp_sent').default(0),
    talkSeconds: integer('talk_seconds').default(0),
    dealsCreatedCount: integer('deals_created_count').default(0),
  },
  (table) => [
    unique('manager_activity_report_date_manager_id_unique').on(
      table.reportDate,
      table.managerId,
    ),
  ],
);

export const kpBriefs = pgTable(
  'kp_briefs',
  {
    id: serial('id').primaryKey(),
    reportDate: date('report_date')
      .notNull()
      .references(() => reports.reportDate),
    itemId: integer('item_id').notNull(),
    dealId: integer('deal_id'),
    title: text('title'),
    itemType: text('item_type').notNull(),
    stage: text('stage'),
    managerId: integer('manager_id'),
    amount: numeric('amount', { precision: 14, scale: 2 }),
  },
  (table) => [
    unique('kp_briefs_report_date_item_id_item_type_unique').on(
      table.reportDate,
      table.itemId,
      table.itemType,
    ),
  ],
);

export const plans = pgTable(
  'plans',
  {
    id: serial('id').primaryKey(),
    period: text('period').notNull(),
    managerId: integer('manager_id'),
    metric: text('metric').notNull(),
    target: numeric('target', { precision: 14, scale: 2 }).notNull(),
  },
  (table) => [
    unique('plans_period_manager_id_metric_unique').on(
      table.period,
      table.managerId,
      table.metric,
    ),
  ],
);
