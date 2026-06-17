import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const MOSCOW_TZ = "Europe/Moscow";

const SRC_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_DIR = path.resolve(SRC_DIR, "..");

function parseEnvFile(filePath) {
  const out = {};
  if (!filePath || !fs.existsSync(filePath)) return out;
  for (const raw of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const idx = line.indexOf("=");
    const k = line.slice(0, idx).trim();
    const v = line.slice(idx + 1).trim().replace(/^"|"$/g, "");
    out[k] = v;
  }
  return out;
}

export function loadEnvFile(pathname = "/etc/openclaw/todo.env") {
  return parseEnvFile(pathname);
}

export function loadMergedEnv() {
  const files = [
    process.env.TODO_ENV_PATH || "",
    "/etc/openclaw/todo.env",
    path.join(PROJECT_DIR, ".env.runtime"),
    path.join(PROJECT_DIR, ".env")
  ];

  const merged = {};
  for (const f of files) {
    Object.assign(merged, parseEnvFile(f));
  }

  return merged;
}

export function getConfig() {
  const fileEnv = loadMergedEnv();
  const env = { ...fileEnv, ...process.env };

  return {
    tz: env.TZ || MOSCOW_TZ,
    provider: (env.TODO_PROVIDER || "todoist").toLowerCase(),
    todoToken: env.TODO_TOKEN || "",
    telegramBotToken: env.TELEGRAM_BOT_TOKEN || "",
    telegramOwnerId: String(env.TELEGRAM_OWNER_ID || "").trim(),

    digestEnabled: String(env.TODO_DAILY_DIGEST_ENABLED || "1") === "1",
    allowTestMessages: String(env.ALLOW_TEST_MESSAGES || "0") === "1",
    todoDryRun: String(env.TODO_DRY_RUN || "0") === "1",

    autoPriorityEnabled: String(env.AUTO_PRIORITY_ENABLED || "1") === "1",
    priorityConfidenceThreshold: Number(env.PRIORITY_CONFIDENCE_THRESHOLD || 0.6),
    eisenhowerEnabled: String(env.EISENHOWER_ENABLED || "1") === "1",
    eisenhowerImportantKeywords: env.EISENHOWER_IMPORTANT_KEYWORDS || "",
    eisenhowerUrgentThreshold: Number(env.EISENHOWER_URGENT_THRESHOLD || 0.6),

    openaiApiKey: env.OPENAI_API_KEY || "",
    voiceMaxDurationSec: Number(env.VOICE_MAX_DURATION_SEC || 180),
    voiceMaxTasks: Number(env.VOICE_MAX_TASKS || 30),

    digestShowMatrix: String(env.DIGEST_SHOW_MATRIX || "1") === "1",
    digestShowPriorityBlock: String(env.DIGEST_SHOW_PRIORITY_BLOCK || "1") === "1",
    digestMaxTasksPerSection: Number(env.DIGEST_MAX_TASKS_PER_SECTION || 3),
    digestMaxTotalTasks: Number(env.DIGEST_MAX_TOTAL_TASKS || 20),
    digestMaxVisibleTasks: Number(env.DIGEST_MAX_VISIBLE_TASKS || 7),
    digestStyle: env.DIGEST_STYLE || "executive",
    digestShortLinkBase: env.DIGEST_SHORTLINK_BASE || "",
    middayReplanEnabled: String(env.MIDDAY_REPLAN_ENABLED || "1") === "1",

    taskReminderPreMin: Number(env.TASK_REMINDER_PRE_MIN || 10),
    taskReminderFollowupMin: Number(env.TASK_REMINDER_FOLLOWUP_MIN || 10),
    reminderStyle: String(env.REMINDER_STYLE || "normal").toLowerCase(),
    remindersEnabledDefault: String(env.REMINDERS_ENABLED_DEFAULT || "1") === "1",

    dndEnabled: String(env.DND_ENABLED || "1") === "1",
    dndNightStart: env.DND_NIGHT_START || "23:00",
    dndNightEnd: env.DND_NIGHT_END || "08:00",
    focusPreferredWindows: env.FOCUS_PREFERRED_WINDOWS || "10:00-11:00,12:00-13:00,15:00-16:00",
    focusPreNotifyMin: Number(env.FOCUS_PRE_NOTIFY_MIN || 5),

    executionModeEnabled: String(env.EXECUTION_MODE_ENABLED || "1") === "1",
    executionCheckMinutes: Number(env.EXECUTION_CHECK_MINUTES || 15),
    executionCooldownMinutes: Number(env.EXECUTION_COOLDOWN_MINUTES || 60),
    executionPreMeetingMin: Number(env.EXECUTION_PRE_MEETING_MIN || 10),
    executionPostMeetingMin: Number(env.EXECUTION_POST_MEETING_MIN || 5),

    profileEnabledDefault: String(env.PROFILE_ENABLED_DEFAULT || "1") === "1",
    personalDataTtlDays: Number(env.PERSONAL_DATA_TTL_DAYS || 180),

    googleClientId: env.GOOGLE_CLIENT_ID || "",
    googleClientSecret: env.GOOGLE_CLIENT_SECRET || "",
    googleRedirectUri: env.GOOGLE_REDIRECT_URI || "",
    googleCalendarIds: String(env.GOOGLE_CALENDAR_IDS || "").split(",").map((x) => x.trim()).filter(Boolean),

    bitrixPortalUrl: env.BITRIX_PORTAL_URL || "",
    bitrixClientId: env.BITRIX_CLIENT_ID || "",
    bitrixClientSecret: env.BITRIX_CLIENT_SECRET || "",
    bitrixRedirectUri: env.BITRIX_REDIRECT_URI || "",
    bitrixUserId: String(env.BITRIX_USER_ID || "").trim(),
    bitrixDefaultSectionId: String(env.BITRIX_DEFAULT_SECTION_ID || "").trim(),
    bitrixCalendarDryRun: String(env.BITRIX_CALENDAR_DRY_RUN || "1") === "1",
    bitrixUsersCacheTtlHours: Number(env.BITRIX_USERS_CACHE_TTL_HOURS || 12),
    bitrixUsersSyncTime: env.BITRIX_USERS_SYNC_TIME || "03:00",
    nameMatchThreshold: Number(env.NAME_MATCH_THRESHOLD || 0.78),
    nameMatchMaxCandidates: Number(env.NAME_MATCH_MAX_CANDIDATES || 8),
    testInviteeName: String(env.TEST_INVITEE_NAME || "").trim(),

    workdayStart: env.WORKDAY_START || "09:00",
    workdayEnd: env.WORKDAY_END || "19:00",
    freeSlotMinMinutes: Number(env.FREE_SLOT_MIN_MINUTES || 30),

    morningSecretaryEnabled: String(env.MORNING_SECRETARY_ENABLED || "1") === "1",
    dayScenarioMessageEnabled: String(env.DAY_SCENARIO_MESSAGE_ENABLED || "1") === "1",
    morningSecretaryTime: env.MORNING_SECRETARY_TIME || "08:00",
    safeMode: String(env.SAFE_MODE || "1") === "1",

    stateDir: env.TODO_STATE_DIR || path.join(PROJECT_DIR, "data")
  };
}
