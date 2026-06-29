import {
  boolean,
  date,
  index,
  integer,
  jsonb,
  numeric,
  pgTable,
  primaryKey,
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
  hiredAt: date('hired_at'),
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

export const liveChats = pgTable('live_chats', {
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
    // Дата последней коммуникации с клиентом (звонок/Wazzup, обе стороны) — для
    // блока «Тишина»: сделки без контакта >14 календарных дней. NULL = контакта не было.
    lastCommAt: date('last_comm_at'),
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
    // Создатель встречи (ТМ): событийная атрибуция «встречу назначил ТМ».
    createdBy: integer('created_by'),
    createdAt: timestamp('created_at', { withTimezone: true }),
    scheduledAt: timestamp('scheduled_at', { withTimezone: true }),
    companyRevenue: numeric('company_revenue', { precision: 20, scale: 2 }),
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
    calls60sPlus: integer('calls_60s_plus').default(0),
    calls120sPlus: integer('calls_120s_plus').default(0),
    dialsTotal: integer('dials_total').default(0),
    meetingsSet: integer('meetings_set').default(0),
    meetingsHeld: integer('meetings_held').default(0),
    briefsCreated: integer('briefs_created').default(0),
    kpSent: integer('kp_sent').default(0),
    talkSeconds: integer('talk_seconds').default(0),
    emailsSent: integer('emails_sent').default(0),
    dealsCreatedCount: integer('deals_created_count').default(0),
    dealsColdCount: integer('deals_cold_count').default(0),
    dealsIncomingCount: integer('deals_incoming_count').default(0),
    dealsWonCount: integer('deals_won_count').default(0),
    dealsWonAmount: numeric('deals_won_amount', { precision: 14, scale: 2 }).default('0'),
    messengerDialogs: integer('messenger_dialogs'),
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
    service: text('service'),
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

export const payments = pgTable(
  'payments',
  {
    id: serial('id').primaryKey(),
    project: text('project'),
    source: text('source'),
    dept: text('dept'),
    manager: text('manager'),
    service: text('service'),
    kdWithVat: numeric('kd_with_vat', { precision: 14, scale: 2 }),
    kdNoVat: numeric('kd_no_vat', { precision: 14, scale: 2 }),
    ddWithVat: numeric('dd_with_vat', { precision: 14, scale: 2 }),
    ddNoVat: numeric('dd_no_vat', { precision: 14, scale: 2 }),
    payDate: text('pay_date'),
    payForm: text('pay_form'),
    counterparty: text('counterparty'),
    brand: text('brand'),
    payMonth: smallint('pay_month'),
    payYear: integer('pay_year'),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [index('payments_year_month_dept_idx').on(table.payYear, table.payMonth, table.dept)],
);

export const managerAbsences = pgTable(
  'manager_absences',
  {
    managerId: integer('manager_id').notNull(),
    absenceDate: date('absence_date').notNull(),
    kind: text('kind'),
  },
  (table) => [primaryKey({ columns: [table.managerId, table.absenceDate] })],
);

export const dealTitles = pgTable('deal_titles', {
  dealId: integer('deal_id').primaryKey(),
  title: text('title'),
  updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
});

export const callHourly = pgTable(
  'call_hourly',
  {
    reportDate: date('report_date').notNull(),
    managerId: integer('manager_id').notNull(),
    hour: smallint('hour').notNull(),
    dials: integer('dials').default(0),
    answered: integer('answered').default(0),
    calls60: integer('calls60').default(0),
  },
  (table) => [
    unique('call_hourly_report_date_manager_id_hour_unique').on(table.reportDate, table.managerId, table.hour),
    index('call_hourly_manager_date_idx').on(table.managerId, table.reportDate),
  ],
);

export const dealRejections = pgTable(
  'deal_rejections',
  {
    dealId: integer('deal_id').primaryKey(),
    categoryId: integer('category_id'),
    stageId: text('stage_id').notNull(),
    reasonId: integer('reason_id'),
    modifiedBy: integer('modified_by'),
    assignedBy: integer('assigned_by'),
    rejectedAt: timestamp('rejected_at', { withTimezone: true }),
    title: text('title'),
    opportunity: numeric('opportunity', { precision: 14, scale: 2 }),
    ownerName: text('owner_name'),
    ownerDept: text('owner_dept'),
    ownerActive: boolean('owner_active'),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [
    index('deal_rejections_modified_by_reason_idx').on(table.modifiedBy, table.reasonId),
    index('deal_rejections_stage_rejected_idx').on(table.stageId, table.rejectedAt),
  ],
);

export const dealWins = pgTable(
  'deal_wins',
  {
    dealId: integer('deal_id').primaryKey(),
    wonDate: date('won_date'),
    opportunity: numeric('opportunity', { precision: 14, scale: 2 }),
    ownerId: integer('owner_id'),
    ownerName: text('owner_name'),
    ownerDept: text('owner_dept'),
    ownerActive: boolean('owner_active'),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [index('deal_wins_won_date_idx').on(table.wonDate)],
);

export const funnelCohort = pgTable(
  'funnel_cohort',
  {
    dealId: integer('deal_id').primaryKey(),
    categoryId: integer('category_id'),
    cohortDate: date('cohort_date'),
    managerId: integer('manager_id'),
    currentStage: text('current_stage'),
    furthestStage: text('furthest_stage'),
    furthestOrder: integer('furthest_order'),
    isWon: boolean('is_won'),
    isLost: boolean('is_lost'),
    opportunity: numeric('opportunity', { precision: 14, scale: 2 }),
    reasonId: integer('reason_id'),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [index('funnel_cohort_cohort_date_manager_idx').on(table.cohortDate, table.managerId)],
);

export const meetingTasks = pgTable(
  'meeting_tasks',
  {
    id: serial('id').primaryKey(),
    reportDate: date('report_date').notNull(),
    meetingId: integer('meeting_id').notNull(),
    dealId: integer('deal_id'),
    stepKey: text('step_key').notNull(),
    taskId: integer('task_id').notNull(),
    responsibleId: integer('responsible_id'),
    title: text('title'),
    deadline: timestamp('deadline', { withTimezone: true }),
    status: integer('status'),
    closed: boolean('closed').notNull().default(false),
    createdAt: timestamp('created_at', { withTimezone: true }),
    updatedAt: timestamp('updated_at', { withTimezone: true }),
  },
  (table) => [unique('meeting_tasks_meeting_id_step_key_unique').on(table.meetingId, table.stepKey)],
);

export const dealRiskFlags = pgTable('deal_risk_flags', {
  dealId: integer('deal_id').primaryKey(),
  title: text('title'),
  stageLabel: text('stage_label'),
  managerId: integer('manager_id'),
  flags: jsonb('flags').notNull().default([]),
  severity: text('severity').notNull().default('warning'),
  checkedAt: timestamp('checked_at', { withTimezone: true }).defaultNow(),
});

export const kpJobs = pgTable(
  'kp_jobs',
  {
    id: serial('id').primaryKey(),
    dealId: integer('deal_id').notNull(),
    brand: text('brand').notNull().default('belberry'),
    service: text('service').notNull().default('seo'),
    status: text('status').notNull().default('pending'),
    stage: text('stage'),
    error: text('error'),
    kpData: jsonb('kp_data'),
    requestedBy: integer('requested_by'),
    createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [
    index('kp_jobs_status_idx').on(table.status),
    index('kp_jobs_deal_idx').on(table.dealId),
  ],
);

export const dealAudits = pgTable(
  'deal_audits',
  {
    id: serial('id').primaryKey(),
    dealId: integer('deal_id').notNull(),
    title: text('title'),
    company: text('company'),
    status: text('status').notNull().default('pending'),
    stage: text('stage'),
    error: text('error'),
    score: integer('score'),
    band: text('band'),
    expectedValue: integer('expected_value'),
    result: jsonb('result'),
    requestedBy: integer('requested_by'),
    returnedToWork: boolean('returned_to_work').notNull().default(false),
    taskId: integer('task_id'),
    outcomeKind: text('outcome_kind'), // current | transferred | telemarketing
    outcomeResponsibleId: integer('outcome_responsible_id'),
    source: text('source').notNull().default('manual'), // manual | auto (радар)
    attempts: integer('attempts').notNull().default(0), // неудачные попытки (транзиентные сбои → повтор)
    returnedAt: timestamp('returned_at', { withTimezone: true }),
    returnStage: text('return_stage'),
    followupStatus: text('followup_status'),   // progressed | stalled | in_progress
    followupNote: text('followup_note'),
    followupAt: timestamp('followup_at', { withTimezone: true }),
    createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [
    index('deal_audits_status_idx').on(table.status),
    index('deal_audits_deal_idx').on(table.dealId),
  ],
);

// Снимок «Команда · эффективность и просрочки» (/alerts/tasks). Наполняет runner
// team_health.py. КПД (наш) + счётчики просрочек на каждого ОП+РОП за день.
export const teamTaskHealth = pgTable(
  'team_task_health',
  {
    reportDate: date('report_date').notNull(),
    managerId: integer('manager_id').notNull(),
    name: text('name'),
    dept: text('dept'),
    isActive: boolean('is_active').notNull().default(true),
    efficiencyPct: numeric('efficiency_pct'),
    closedWithDeadline: integer('closed_with_deadline').notNull().default(0),
    closedOntime: integer('closed_ontime').notNull().default(0),
    overdueTasks: integer('overdue_tasks').notNull().default(0),
    overdueActivities: integer('overdue_activities').notNull().default(0),
    collectedAt: timestamp('collected_at', { withTimezone: true }).defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.reportDate, table.managerId] })],
);
