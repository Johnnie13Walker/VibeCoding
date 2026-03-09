set -euo pipefail
export TZ=Europe/Moscow

project_path='/root/.openclaw/workspace/todo-integration'
container_name='openclaw-openclaw-gateway-1'
cron_file='/etc/cron.d/openclaw-todo-digest'

[ -d "$project_path" ] || { echo "Каталог проекта не найден: $project_path"; exit 1; }

backup_dir="$project_path/.backups/todo_digest_fix_$(date '+%Y%m%d_%H%M%S_MSK')"
mkdir -p "$backup_dir/src/providers" "$backup_dir/src/agenda" "$backup_dir/src/reports" "$backup_dir/src/selftests" "$backup_dir/system"

cp -a "$project_path/src/send-digest.mjs" "$backup_dir/src/send-digest.mjs.bak"
cp -a "$project_path/src/providers/todoist-provider.mjs" "$backup_dir/src/providers/todoist-provider.mjs.bak"
cp -a "$project_path/src/agenda/aggregate.mjs" "$backup_dir/src/agenda/aggregate.mjs.bak"
cp -a "$project_path/src/reports/morningSecretaryDigest.mjs" "$backup_dir/src/reports/morningSecretaryDigest.mjs.bak"
if [ -f "$project_path/src/reports/calendarDailyRenderer.mjs" ]; then
  cp -a "$project_path/src/reports/calendarDailyRenderer.mjs" "$backup_dir/src/reports/calendarDailyRenderer.mjs.bak"
fi
cp -a "$project_path/src/agenda-query.mjs" "$backup_dir/src/agenda-query.mjs.bak"
if [ -f "$project_path/src/selftests/calendarDailyRenderer.smoke.mjs" ]; then
  cp -a "$project_path/src/selftests/calendarDailyRenderer.smoke.mjs" "$backup_dir/src/selftests/calendarDailyRenderer.smoke.mjs.bak"
fi
cp -a "$project_path/src/add-task-flow.mjs" "$backup_dir/src/add-task-flow.mjs.bak"
cp -a "$project_path/src/formatter.mjs" "$backup_dir/src/formatter.mjs.bak"
cp -a "$project_path/src/selftest.mjs" "$backup_dir/src/selftest.mjs.bak"
if [ -f "$cron_file" ]; then
  cp -a "$cron_file" "$backup_dir/system/openclaw-todo-digest.cron.bak"
fi
if [ -f /root/.openclaw/openclaw.json ]; then
  cp -a /root/.openclaw/openclaw.json "$backup_dir/system/openclaw.json.bak"
fi

cat >"$project_path/src/providers/todoist-provider.mjs" <<'EOF_PROVIDER'
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** @implements {import('./types.mjs').ToDoProvider} */
export class TodoistProvider {
  constructor({ token, fetchImpl = fetch, logger = console, maxAttempts = 3 }) {
    this.token = token;
    this.fetchImpl = fetchImpl;
    this.logger = logger;
    this.baseUrl = "https://api.todoist.com/api/v1";
    this.maxAttempts = Math.max(1, Number(maxAttempts || 3));
  }

  isRetryableStatus(status) {
    const n = Number(status);
    return n >= 500 && n <= 599;
  }

  backoffMs(attempt) {
    const base = 500 * (2 ** Math.max(0, attempt - 1));
    const jitter = Math.floor(Math.random() * 250);
    return base + jitter;
  }

  async requestWithRetry({ path, method = "GET", body = null }) {
    let lastError = null;

    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        const res = await this.fetchImpl(path, {
          method,
          headers: {
            Authorization: `Bearer ${this.token}`,
            Accept: "application/json",
            ...(body ? { "Content-Type": "application/json" } : {})
          },
          ...(body ? { body: JSON.stringify(body) } : {})
        });

        const text = await res.text();
        if (res.ok) {
          if (!text) return {};
          try {
            return JSON.parse(text);
          } catch {
            return {};
          }
        }

        const error = new Error(`Todoist API error ${res.status}: ${text.slice(0, 240)}`);
        lastError = error;

        if (this.isRetryableStatus(res.status) && attempt < this.maxAttempts) {
          const waitMs = this.backoffMs(attempt);
          this.logger.warn?.(`[todoist] retry attempt=${attempt + 1}/${this.maxAttempts} wait_ms=${waitMs} status=${res.status}`);
          await sleep(waitMs);
          continue;
        }

        throw error;
      } catch (err) {
        lastError = err;
        if (attempt < this.maxAttempts) {
          const waitMs = this.backoffMs(attempt);
          this.logger.warn?.(`[todoist] retry attempt=${attempt + 1}/${this.maxAttempts} wait_ms=${waitMs} error=${err?.message || err}`);
          await sleep(waitMs);
          continue;
        }
        throw err;
      }
    }

    throw lastError || new Error("Todoist request failed");
  }

  async request(pathWithQuery) {
    return this.requestWithRetry({
      path: `${this.baseUrl}${pathWithQuery}`,
      method: "GET"
    });
  }

  async requestPost(path, body) {
    return this.requestWithRetry({
      path: `${this.baseUrl}${path}`,
      method: "POST",
      body
    });
  }

  normalizeTask(task) {
    const due = task?.due || {};
    return {
      id: String(task?.id ?? ""),
      content: task?.content || "(без названия)",
      dueDateTime: due?.datetime || null,
      dueDate: due?.date || null,
      url: task?.url || null,
      projectName: null,
      completed: !!task?.checked || !!task?.completed_at,
      priority: Number(task?.priority || 2)
    };
  }

  isTaskCompleted(task) {
    return !!task?.completed;
  }

  async getAllOpenTasks(limit = 200) {
    const all = [];
    let cursor = null;

    while (all.length < limit) {
      const qs = new URLSearchParams({ limit: "100" });
      if (cursor) qs.set("cursor", cursor);
      const payload = await this.request(`/tasks?${qs.toString()}`);
      const items = (payload?.results || []).map((x) => this.normalizeTask(x));
      all.push(...items);
      cursor = payload?.next_cursor || null;
      if (!cursor || !items.length) break;
    }

    return all.slice(0, limit);
  }

  async getTasksForDate(dateISO) {
    const all = await this.getAllOpenTasks();
    return all.filter((t) => t.dueDate === dateISO && !this.isTaskCompleted(t));
  }

  async getOverdueAndToday(dateISO) {
    const all = await this.getAllOpenTasks();
    return all.filter((t) => t.dueDate && t.dueDate <= dateISO && !this.isTaskCompleted(t));
  }

  async createTask({ content, dueDate = null, dueDateTime = null, dueString = null, priority = 2 }) {
    const payload = { content, priority };
    if (dueDateTime) payload.due_datetime = dueDateTime;
    else if (dueDate) payload.due_date = dueDate;
    else if (dueString) payload.due_string = dueString;

    const created = await this.requestPost("/tasks", payload);
    return this.normalizeTask(created);
  }

  async updateTaskDue(taskId, { dueDate = null, dueDateTime = null }) {
    const payload = {};
    if (dueDateTime) payload.due_datetime = dueDateTime;
    else if (dueDate) payload.due_date = dueDate;
    const updated = await this.requestPost(`/tasks/${encodeURIComponent(String(taskId))}`, payload);
    return this.normalizeTask(updated);
  }
}
EOF_PROVIDER

cat >"$project_path/src/agenda/aggregate.mjs" <<'EOF_AGG'
import { createProvider } from "../provider-factory.mjs";
import { filterOverdue, filterTasksForDate } from "../service.mjs";
import { dedupeMeetings } from "./merge.mjs";
import { computeFreeSlots } from "./freeSlots.mjs";
import { fetchGoogleAgendaForDate, googleConnected } from "./providers/googleCalendar.mjs";
import { fetchBitrixAgendaForDate, bitrixConnected } from "./providers/bitrixCalendar.mjs";
import { markAgendaSync } from "./state.mjs";
import { collectAgendaTelemetry } from "../personal/telemetryCollector.mjs";

function mapTaskPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function pickFocus(tasks) {
  return tasks
    .map((t) => ({ ...t, displayPriority: mapTaskPriority(t) }))
    .sort((a, b) => a.displayPriority - b.displayPriority)
    .slice(0, 2);
}

function normalizeError(err) {
  return String(err?.message || err || "todo_unavailable")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
}

function dateIsoInTz(dt, tz = "Europe/Moscow") {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date(dt));

  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !d) return null;
  return `${y}-${m}-${d}`;
}

function filterMeetingsByDate(meetings, dateISO, tz) {
  return (meetings || []).filter((m) => {
    if (!m?.start) return false;
    const startIso = dateIsoInTz(m.start, tz);
    if (!startIso) return false;
    if (startIso === dateISO) return true;

    if (!m?.end) return false;
    const endIso = dateIsoInTz(m.end, tz);
    if (!endIso) return false;
    return dateISO >= startIso && dateISO <= endIso;
  });
}

export async function getAgenda(cfg, dateISO, opts = {}) {
  const prefetchedTasks = Array.isArray(opts.prefetchedTasks) ? opts.prefetchedTasks : null;
  const skipTodoFetch = opts.skipTodoFetch === true;
  const todoWarning = String(opts.todoWarning || "").trim();

  let allTasks = [];
  let todoConnected = true;
  let todoIssue = "";

  if (skipTodoFetch) {
    allTasks = prefetchedTasks || [];
    todoConnected = false;
    todoIssue = todoWarning || "todo_fetch_skipped";
    markAgendaSync(cfg.stateDir, "todo", false, todoIssue);
  } else if (prefetchedTasks !== null) {
    allTasks = prefetchedTasks;
    markAgendaSync(cfg.stateDir, "todo", true);
  } else {
    try {
      const provider = createProvider(cfg);
      allTasks = await provider.getAllOpenTasks();
      markAgendaSync(cfg.stateDir, "todo", true);
    } catch (err) {
      allTasks = [];
      todoConnected = false;
      todoIssue = normalizeError(err);
      markAgendaSync(cfg.stateDir, "todo", false, todoIssue);
    }
  }

  const tasks = filterTasksForDate(allTasks, dateISO);
  const overdue = filterOverdue(allTasks, dateISO);

  const [googleIsConnected, bitrixIsConnected] = await Promise.all([
    googleConnected(cfg),
    bitrixConnected(cfg)
  ]);

  const [googleMeetings, bitrixMeetings] = await Promise.all([
    fetchGoogleAgendaForDate(cfg, dateISO),
    fetchBitrixAgendaForDate(cfg, dateISO)
  ]);

  const dedupedMeetings = dedupeMeetings([...(googleMeetings || []), ...(bitrixMeetings || [])]);
  const meetings = filterMeetingsByDate(dedupedMeetings, dateISO, cfg.tz);
  const freeSlots = computeFreeSlots(meetings, {
    tz: cfg.tz,
    workdayStart: cfg.workdayStart,
    workdayEnd: cfg.workdayEnd,
    minMinutes: cfg.freeSlotMinMinutes
  });

  const focus = pickFocus(tasks);

  const result = {
    date: dateISO,
    meetings,
    tasks,
    overdueCount: overdue.length,
    freeSlots,
    focus,
    sourceStatus: {
      googleConnected: !!googleIsConnected,
      bitrixConnected: !!bitrixIsConnected,
      todoConnected
    }
  };

  if (!todoConnected) {
    result.sourceWarnings = { todo: todoIssue || "todo_unavailable" };
  }

  try {
    collectAgendaTelemetry(cfg, result);
  } catch {
    // no-op telemetry failure
  }

  return result;
}
EOF_AGG

cat >"$project_path/src/reports/calendarDailyRenderer.mjs" <<'EOF_CAL_RENDERER'
function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cleanText(v = "") {
  return String(v || "").replace(/\s+/g, " ").trim();
}

function asArray(v) {
  return Array.isArray(v) ? v : [];
}

function normalizeUserToken(v) {
  const raw = cleanText(v);
  if (!raw) return null;
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return { id: m[1], code: `U${m[1]}`, raw };
  if (/^\d+$/.test(raw)) return { id: raw, code: `U${raw}`, raw };
  return { id: null, code: raw.toUpperCase(), raw };
}

function buildIdentity(input) {
  const ids = new Set();
  const codes = new Set();

  const add = (value) => {
    const t = normalizeUserToken(value);
    if (!t) return;
    if (t.id) ids.add(t.id);
    if (t.code) codes.add(t.code);
  };

  if (input && typeof input === "object" && !Array.isArray(input)) {
    add(input.myUserId);
    add(input.myUserCode);
    add(input.userId);
    add(input.userCode);
    add(input.id);
    add(input.code);
  } else {
    add(input);
  }

  return { ids, codes };
}

function isSelf(value, identity) {
  const t = normalizeUserToken(value);
  if (!t) return false;
  if (t.id && identity.ids.has(t.id)) return true;
  if (t.code && identity.codes.has(t.code)) return true;
  return false;
}

function isPersonalTitle(title = "") {
  return /(обед|еда|спорт|трен|дорога|перерыв|врач|семья|садик|школа)/i.test(String(title || ""));
}

function hasOwn(obj, key) {
  return !!(obj && Object.prototype.hasOwnProperty.call(obj, key));
}

function collectMeetingParticipants(event) {
  const values = [];
  let hasField = false;

  if (event?.MEETING && typeof event.MEETING === "object") {
    hasField = true;
    values.push(...asArray(event.MEETING.PARTICIPANTS));
    values.push(...asArray(event.MEETING.PARTICIPANTS_CODES));
    values.push(...asArray(event.MEETING.USERS));
    if (event.MEETING.HOST != null) values.push(event.MEETING.HOST);
  }

  if (event?.host != null) {
    hasField = true;
    values.push(event.host);
  }
  if (event?.HOST != null) {
    hasField = true;
    values.push(event.HOST);
  }
  if (hasOwn(event, "participants")) {
    hasField = true;
    values.push(...asArray(event.participants));
  }
  if (hasOwn(event, "PARTICIPANTS")) {
    hasField = true;
    values.push(...asArray(event.PARTICIPANTS));
  }

  return { values, hasField };
}

function extractParticipantToken(entry) {
  if (entry == null) return null;
  if (typeof entry === "string" || typeof entry === "number") return entry;
  if (typeof entry !== "object") return null;
  return (
    entry.USER_ID
    ?? entry.userId
    ?? entry.ID
    ?? entry.id
    ?? entry.ENTITY_ID
    ?? entry.entityId
    ?? entry.CODE
    ?? entry.code
    ?? entry.USER_CODE
    ?? entry.userCode
    ?? null
  );
}

function hasOthersInList(values, identity) {
  const filtered = values
    .map((entry) => extractParticipantToken(entry) ?? entry)
    .map((entry) => cleanText(entry))
    .filter(Boolean);
  if (!filtered.length) return false;
  return filtered.some((x) => !isSelf(x, identity));
}

export function classifyBitrixEvent(event, myUserIdOrCode) {
  const identity = buildIdentity(myUserIdOrCode);
  const title = String(event?.title || event?.NAME || event?.name || "");

  const hasCodesField = hasOwn(event, "ATTENDEES_CODES") || hasOwn(event, "attendeesCodes");
  if (hasCodesField) {
    const codes = [...asArray(event?.ATTENDEES_CODES), ...asArray(event?.attendeesCodes)];
    if (hasOthersInList(codes, identity)) return "meeting";
    return isPersonalTitle(title) ? "personal_block" : "work_block";
  }

  const hasAttendeesField = hasOwn(event, "attendees") || hasOwn(event, "ATTENDEES") || hasOwn(event, "ATTENDEE_LIST");
  if (hasAttendeesField) {
    const attendees = [...asArray(event?.attendees), ...asArray(event?.ATTENDEES), ...asArray(event?.ATTENDEE_LIST)];
    if (hasOthersInList(attendees, identity)) return "meeting";
    return isPersonalTitle(title) ? "personal_block" : "work_block";
  }

  const isMeetingFlag = event?.IS_MEETING === true || event?.isMeeting === true || String(event?.IS_MEETING || "").toLowerCase() === "true";
  const participants = collectMeetingParticipants(event);
  if (isMeetingFlag && participants.hasField) {
    if (hasOthersInList(participants.values, identity)) return "meeting";
    return isPersonalTitle(title) ? "personal_block" : "work_block";
  }

  return "work_block";
}

function normalizeFallbackUser(entry) {
  const raw = cleanText(entry);
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw;
}

function displayNameFromObject(obj = {}) {
  const full = cleanText(obj.FULL_NAME || obj.fullName || obj.DISPLAY_NAME || obj.displayName);
  if (full) return full;
  const first = cleanText(obj.NAME || obj.name || obj.FIRST_NAME || obj.firstName);
  const last = cleanText(obj.LAST_NAME || obj.lastName || obj.SURNAME || obj.surname);
  const joined = cleanText(`${first} ${last}`);
  if (joined) return joined;
  const title = cleanText(obj.TITLE || obj.title);
  if (title) return title;
  const email = cleanText(obj.EMAIL || obj.email);
  if (email) return email;
  const login = cleanText(obj.LOGIN || obj.login);
  if (login) return login;

  const token = extractParticipantToken(obj);
  return normalizeFallbackUser(token);
}

function pushUnique(out, seen, value) {
  const clean = cleanText(value);
  if (!clean) return;
  if (clean === "[object Object]") return;
  if (seen.has(clean.toLowerCase())) return;
  seen.add(clean.toLowerCase());
  out.push(clean);
}

export function extractOtherAttendees(event, myUserCode) {
  const identity = buildIdentity(myUserCode);
  const out = [];
  const seen = new Set();

  const attendeeArrays = [event?.attendees, event?.ATTENDEES, event?.ATTENDEE_LIST];
  attendeeArrays.forEach((arr) => {
    asArray(arr).forEach((entry) => {
      if (typeof entry === "string" || typeof entry === "number") {
        if (isSelf(entry, identity)) return;
        const name = normalizeFallbackUser(entry);
        pushUnique(out, seen, name);
        return;
      }
      if (entry && typeof entry === "object") {
        const token = extractParticipantToken(entry);
        if (token != null && isSelf(token, identity)) return;
        const name = displayNameFromObject(entry);
        pushUnique(out, seen, name);
      }
    });
  });

  const fallbackTokens = [
    ...asArray(event?.attendeeIds),
    ...asArray(event?.ATTENDEES_CODES),
    ...asArray(event?.attendeesCodes),
    ...collectMeetingParticipants(event).values.map((x) => extractParticipantToken(x) ?? x)
  ];

  fallbackTokens.forEach((token) => {
    if (token == null || isSelf(token, identity)) return;
    const display = normalizeFallbackUser(token);
    pushUnique(out, seen, display);
  });

  return out;
}

function pluralRu(n, one, few, many) {
  const v = Math.abs(Number(n || 0)) % 100;
  const rem = v % 10;
  if (v > 10 && v < 20) return many;
  if (rem > 1 && rem < 5) return few;
  if (rem === 1) return one;
  return many;
}

function dateIsoNow(tz = "Europe/Moscow") {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !d) return "1970-01-01";
  return `${y}-${m}-${d}`;
}

function dateTitle(dateISO, tz = "Europe/Moscow") {
  const dt = new Date(`${dateISO}T00:00:00+03:00`);
  if (!Number.isFinite(dt.getTime())) return dateISO;
  const raw = new Intl.DateTimeFormat("ru-RU", {
    timeZone: tz,
    weekday: "long",
    day: "numeric",
    month: "long"
  }).format(dt);
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function hhmm(dt, tz = "Europe/Moscow") {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function eventRange(event, tz) {
  if (event?.isAllDay) return "Весь день";
  const start = new Date(event?.start || "");
  const end = new Date(event?.end || "");
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) return "Время уточняется";
  return `${hhmm(start, tz)}–${hhmm(end, tz)}`;
}

function slotDurationMin(slot) {
  const a = String(slot?.start || "").match(/^(\d{2}):(\d{2})$/);
  const b = String(slot?.end || "").match(/^(\d{2}):(\d{2})$/);
  if (!a || !b) return 0;
  const s = Number(a[1]) * 60 + Number(a[2]);
  const e = Number(b[1]) * 60 + Number(b[2]);
  return Math.max(0, e - s);
}

function sortByStart(events) {
  return [...events].sort((a, b) => {
    const sa = new Date(a?.start || 0).getTime();
    const sb = new Date(b?.start || 0).getTime();
    if (sa !== sb) return sa - sb;
    const ea = new Date(a?.end || 0).getTime();
    const eb = new Date(b?.end || 0).getTime();
    return ea - eb;
  });
}

function limitLinesByItems(items, toLines, maxContentLines = 6) {
  const lines = [];
  let shownItems = 0;

  for (let i = 0; i < items.length; i += 1) {
    const chunk = toLines(items[i]);
    if (lines.length + chunk.length > maxContentLines) break;
    lines.push(...chunk);
    shownItems += 1;
  }

  if (shownItems < items.length) {
    lines.push(`+${items.length - shownItems}`);
  }

  return lines;
}

function buildRisks({ meetingCount, workCount, focusWindows }) {
  const totalFocusMin = focusWindows.reduce((acc, slot) => acc + slotDurationMin(slot), 0);
  const out = [];

  if (totalFocusMin < 90) {
    out.push("Мало времени для фокус-работы");
  }
  if (meetingCount >= 7) {
    out.push("Перегруз встречами — может просесть выполнение задач");
  }
  if (workCount === 0) {
    out.push("Нет выделенных рабочих блоков");
  }

  return out.slice(0, 3);
}

function normalizeMyUserCode(input) {
  const raw = cleanText(input);
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

export function renderDailyCalendarDigest(data) {
  const agenda = data?.agenda || data || {};
  const cfg = data?.cfg || {};
  const tz = data?.tz || cfg?.tz || "Europe/Moscow";
  const myUserCode = normalizeMyUserCode(data?.myUserCode || data?.myUserId || cfg?.bitrixUserId || "");
  const events = sortByStart(asArray(agenda?.meetings));

  const buckets = {
    meeting: [],
    work_block: [],
    personal_block: []
  };

  events.forEach((event) => {
    const type = classifyBitrixEvent(event, { myUserCode, myUserId: cfg?.bitrixUserId });
    if (!buckets[type]) buckets.work_block.push(event);
    else buckets[type].push(event);
  });

  const focusWindows = asArray(agenda?.freeSlots).filter((slot) => slotDurationMin(slot) >= 45);
  const risks = buildRisks({
    meetingCount: buckets.meeting.length,
    workCount: buckets.work_block.length,
    focusWindows
  });

  const todayIso = cleanText(agenda?.date) || dateIsoNow(tz);
  const summary = [
    `${buckets.meeting.length} ${pluralRu(buckets.meeting.length, "встреча", "встречи", "встреч")}`,
    `${buckets.work_block.length} ${pluralRu(buckets.work_block.length, "блок работы", "блока работы", "блоков работы")}`,
    `${buckets.personal_block.length} ${pluralRu(buckets.personal_block.length, "личный блок", "личных блока", "личных блоков")}`,
    `${focusWindows.length} ${pluralRu(focusWindows.length, "окно фокуса", "окна фокуса", "окон фокуса")}`
  ].join(" • ");

  const blocks = [];

  if (buckets.meeting.length) {
    const lines = limitLinesByItems(buckets.meeting, (event) => {
      const base = [`${eventRange(event, tz)}  ${escapeHtml(cleanText(event?.title || "Без названия"))}`];
      const attendees = extractOtherAttendees(event, myUserCode);
      if (attendees.length) {
        const shown = attendees.slice(0, 5).map((name) => escapeHtml(cleanText(name)));
        const extra = attendees.length > shown.length ? `, +${attendees.length - shown.length}` : "";
        base.push(`(${shown.join(", ")}${extra})`);
      }
      return base;
    });
    blocks.push({ title: "🤝 <b>ВСТРЕЧИ</b>", lines });
  }

  if (buckets.work_block.length) {
    const lines = limitLinesByItems(
      buckets.work_block,
      (event) => [`${eventRange(event, tz)}  ${escapeHtml(cleanText(event?.title || "Без названия"))}`]
    );
    blocks.push({ title: "🧠 <b>МОИ БЛОКИ РАБОТЫ</b>", lines });
  }

  if (buckets.personal_block.length) {
    const lines = limitLinesByItems(
      buckets.personal_block,
      (event) => [`${eventRange(event, tz)}  ${escapeHtml(cleanText(event?.title || "Без названия"))}`]
    );
    blocks.push({ title: "🍽 <b>ЛИЧНОЕ</b>", lines });
  }

  if (focusWindows.length) {
    const lines = limitLinesByItems(
      focusWindows,
      (slot) => [`${slot.start}–${slot.end}  глубокая работа`]
    );
    blocks.push({ title: "🟢 <b>ОКНО ФОКУСА</b>", lines });
  } else {
    blocks.push({ title: "", lines: ["⚠️ <b>Нет свободных окон</b>"] });
  }

  if (risks.length) {
    blocks.push({ title: "⚠️ <b>РИСКИ ДНЯ</b>", lines: risks.map((risk) => `• ${escapeHtml(risk)}`) });
  }

  const firstWork = buckets.work_block[0] || null;
  blocks.push({
    title: "➡️ <b>НАЧАТЬ СЕЙЧАС</b>",
    lines: [
      firstWork
        ? `${eventRange(firstWork, tz)}  ${escapeHtml(cleanText(firstWork?.title || "Без названия"))}`
        : "Выбери главный фокус"
    ]
  });

  const out = [
    `☀️ <b>${escapeHtml(dateTitle(todayIso, tz))}</b>`,
    "",
    `📊 День: ${summary}`
  ];

  blocks.forEach((block) => {
    if (!block.lines?.length) return;
    out.push("", "────────", "");
    if (block.title) out.push(block.title);
    out.push(...block.lines);
  });

  return out.join("\n");
}
EOF_CAL_RENDERER

cat >"$project_path/src/reports/morningSecretaryDigest.mjs" <<'EOF_MORNING'
import { extractOtherAttendees, renderDailyCalendarDigest } from "./calendarDailyRenderer.mjs";

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function hhmm(dt, tz = "Europe/Moscow") {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function normalizeMyUserCode(cfg = {}) {
  const raw = String(cfg?.bitrixUserId || "").trim();
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

function formatAttendeesInline(list = []) {
  const names = list.map((x) => String(x || "").trim()).filter(Boolean);
  if (!names.length) return "";
  const shown = names.slice(0, 5).map((x) => `<b>${escapeHtml(x)}</b>`);
  const extra = names.length - shown.length;
  return extra > 0 ? ` (с: ${shown.join(", ")} + ещё ${extra})` : ` (с: ${shown.join(", ")})`;
}

export function formatMeetingLine(meeting, cfg) {
  const tz = cfg?.tz || "Europe/Moscow";
  const time = meeting?.isAllDay ? "Весь день" : `${hhmm(meeting?.start, tz)}–${hhmm(meeting?.end, tz)}`;
  const attendees = extractOtherAttendees(meeting, normalizeMyUserCode(cfg));
  return `${time}  ${escapeHtml(meeting?.title || "Без названия")}${formatAttendeesInline(attendees)}`;
}

export function formatMorningSecretaryDigest(agenda, cfg, opts = {}) {
  let text = renderDailyCalendarDigest({
    agenda,
    cfg,
    myUserCode: normalizeMyUserCode(cfg)
  });

  if (opts.withHintTomorrow) {
    text += "\n\nКоманда: /day tomorrow";
  }

  return text;
}

export function formatAgendaOnly(agenda, cfg) {
  const meetings = Array.isArray(agenda?.meetings) ? agenda.meetings : [];
  const date = String(agenda?.date || "");
  const dateLabel = date ? `${date.slice(8, 10)}.${date.slice(5, 7)}.${date.slice(0, 4)}` : date;
  const lines = [`Календарь на ${dateLabel}`, ""];
  if (!meetings.length) return `Календарь на ${dateLabel}\n\nНа этот день встреч нет.`;
  meetings.slice(0, 20).forEach((m, i) => lines.push(`${i + 1}. ${formatMeetingLine(m, cfg)}`));
  if (meetings.length > 20) lines.push(`ещё ${meetings.length - 20}`);
  return lines.join("\n");
}

export function formatFreeSlotsOnly(agenda) {
  const free = Array.isArray(agenda?.freeSlots) ? agenda.freeSlots : [];
  if (!free.length) return "Свободные слоты\n\nСвободных окон нет.";
  return ["Свободные слоты", "", ...free.map((s) => `${s.start}–${s.end}`)].join("\n");
}
EOF_MORNING

cat >"$project_path/src/agenda-query.mjs" <<'EOF_AGENDA_QUERY'
import { fileURLToPath } from "node:url";
import { getConfig } from "./config.mjs";
import { dateISOInTz, parseMoscowDateArg } from "./time.mjs";
import { getAgenda } from "./agenda/aggregate.mjs";
import { formatAgendaOnly, formatFreeSlotsOnly, formatMorningSecretaryDigest } from "./reports/morningSecretaryDigest.mjs";
import { classifyBitrixEvent, extractOtherAttendees } from "./reports/calendarDailyRenderer.mjs";
import { buildGoogleConnectUrl, completeGoogleConnect, googleConnected } from "./agenda/providers/googleCalendar.mjs";
import { bitrixConnected, buildBitrixConnectUrl, completeBitrixConnect } from "./agenda/providers/bitrixCalendar.mjs";
import { getBitrixUsersSyncMeta } from "./agenda/providers/bitrixUsers.mjs";
import { loadAgendaSyncStatus } from "./agenda/state.mjs";
import { createProvider } from "./provider-factory.mjs";

function parseDateArgOrToday(arg, todayIso) {
  if (!arg) return { ok: true, iso: todayIso };
  return parseMoscowDateArg(arg, todayIso);
}

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toMyUserCode(cfg) {
  const raw = String(cfg?.bitrixUserId || "").trim();
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

function diagSampleLine(label, event, myUserCode) {
  if (!event) return `<b>${label}:</b> —`;
  const title = escapeHtml(event?.title || event?.NAME || event?.name || "Без названия");
  const count = extractOtherAttendees(event, myUserCode).length;
  return `<b>${label}:</b> ${title} (участников: ${count})`;
}

function formatDiagHtml({ agenda, cfg, dateIso }) {
  const myUserCode = toMyUserCode(cfg);
  const events = Array.isArray(agenda?.meetings) ? agenda.meetings : [];
  const buckets = {
    meeting: [],
    work_block: [],
    personal_block: []
  };

  events.forEach((event) => {
    const type = classifyBitrixEvent(event, { myUserId: cfg?.bitrixUserId, myUserCode });
    if (!buckets[type]) buckets.work_block.push(event);
    else buckets[type].push(event);
  });

  return [
    "🧪 <b>/diag календаря</b>",
    `<b>timezone:</b> ${escapeHtml(cfg?.tz || "Europe/Moscow")}`,
    `<b>myUserCode:</b> ${escapeHtml(myUserCode || "не задан")}`,
    `<b>дата:</b> ${escapeHtml(dateIso)}`,
    `<b>событий получено:</b> ${events.length}`,
    `<b>classified:</b> meetings=${buckets.meeting.length} • work=${buckets.work_block.length} • personal=${buckets.personal_block.length}`,
    diagSampleLine("meeting", buckets.meeting[0], myUserCode),
    diagSampleLine("work_block", buckets.work_block[0], myUserCode),
    diagSampleLine("personal_block", buckets.personal_block[0], myUserCode)
  ].join("\n");
}

export async function runAgendaCommand(cmdRaw, argRaw = "") {
  const cmd = String(cmdRaw || "").trim().toLowerCase();
  const arg = String(argRaw || "").trim();
  const cfg = getConfig();
  const todayIso = dateISOInTz(new Date(), cfg.tz);

  if (cmd === "connect_google") {
    const r = buildGoogleConnectUrl(cfg);
    if (!r.ok) return r.error;
    return `Подключение Google Calendar:\n${r.url}\n\nПосле авторизации пришлите: /oauth_google <callback_url>`;
  }

  if (cmd === "oauth_google") {
    const r = await completeGoogleConnect(cfg, arg);
    return r.ok ? "Google Calendar подключено ✅" : `Google connect error: ${r.error}`;
  }

  if (cmd === "connect_bitrix") {
    const r = buildBitrixConnectUrl(cfg);
    if (!r.ok) return r.error;
    return `Подключение Bitrix24 Calendar:\n${r.url}\n\nПосле авторизации пришлите: /oauth_bitrix <callback_url>`;
  }

  if (cmd === "oauth_bitrix") {
    const r = await completeBitrixConnect(cfg, arg);
    return r.ok ? "Bitrix24 Calendar подключено ✅" : `Bitrix connect error: ${r.error}`;
  }

  if (cmd === "sync_status") {
    const status = loadAgendaSyncStatus(cfg.stateDir);
    const g = await googleConnected(cfg);
    const b = await bitrixConnected(cfg);

    let todoOk = false;
    try {
      const p = createProvider(cfg);
      await p.getTasksForDate(todayIso);
      todoOk = true;
    } catch {
      todoOk = false;
    }

    const usersMeta = getBitrixUsersSyncMeta(cfg.stateDir);

    return [
      "🔄 Статус синхронизации",
      `Google: ${g ? "connected" : "not connected"}${status.google?.last_success_at ? ` (last: ${status.google.last_success_at})` : ""}`,
      `Bitrix: ${b ? "connected" : "not connected"}${status.bitrix?.last_success_at ? ` (last: ${status.bitrix.last_success_at})` : ""}`,
      `Bitrix users: ${usersMeta.lastSyncStatus || "unknown"}${usersMeta.lastSyncAt ? ` (last: ${usersMeta.lastSyncAt})` : ""}`,
      `To-do: ${todoOk ? "connected" : "not connected"}${status.todo?.last_success_at ? ` (last: ${status.todo.last_success_at})` : ""}`
    ].join("\n");
  }

  if (cmd === "diag") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatDiagHtml({ agenda, cfg, dateIso: parsed.iso });
  }

  if (cmd === "agenda") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatAgendaOnly(agenda, cfg);
  }

  if (cmd === "free") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatFreeSlotsOnly(agenda, cfg);
  }

  if (cmd === "day") {
    const parsed = parseDateArgOrToday(arg, todayIso);
    if (!parsed.ok) return parsed.error;
    const agenda = await getAgenda(cfg, parsed.iso);
    return formatMorningSecretaryDigest(agenda, cfg, { withHintTomorrow: false });
  }

  if (cmd === "morning_secretary") {
    const agenda = await getAgenda(cfg, todayIso);
    return formatMorningSecretaryDigest(agenda, cfg, { withHintTomorrow: true });
  }

  return "__NOOP__";
}

async function main() {
  const cmd = process.argv[2] || "";
  const arg = process.argv.slice(3).join(" ");
  const text = await runAgendaCommand(cmd, arg);
  console.log(text);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
EOF_AGENDA_QUERY

mkdir -p "$project_path/src/selftests"
cat >"$project_path/src/selftests/calendarDailyRenderer.smoke.mjs" <<'EOF_CAL_SMOKE'
import { classifyBitrixEvent, renderDailyCalendarDigest } from "../reports/calendarDailyRenderer.mjs";

const myUserCode = "U12";
const dateIso = "2026-03-04";

const mockEvents = [
  {
    id: "m1",
    title: "Встреча с Романом",
    start: `${dateIso}T08:30:00+03:00`,
    end: `${dateIso}T09:00:00+03:00`,
    ATTENDEES_CODES: ["U12", "U77"],
    attendees: ["Роман"]
  },
  {
    id: "w1",
    title: "Подготовить отчёт",
    start: `${dateIso}T10:00:00+03:00`,
    end: `${dateIso}T11:00:00+03:00`,
    ATTENDEES_CODES: ["U12"]
  },
  {
    id: "p1",
    title: "Обед",
    start: `${dateIso}T13:00:00+03:00`,
    end: `${dateIso}T14:00:00+03:00`,
    ATTENDEES_CODES: ["U12"]
  }
];

const expectedTypes = ["meeting", "work_block", "personal_block"];
const actualTypes = mockEvents.map((event) => classifyBitrixEvent(event, myUserCode));

if (JSON.stringify(expectedTypes) !== JSON.stringify(actualTypes)) {
  throw new Error(`calendar_renderer_smoke: classify mismatch expected=${JSON.stringify(expectedTypes)} actual=${JSON.stringify(actualTypes)}`);
}

const digest = renderDailyCalendarDigest({
  agenda: {
    date: dateIso,
    meetings: mockEvents,
    freeSlots: [{ start: "15:00", end: "17:00" }]
  },
  cfg: { tz: "Europe/Moscow", bitrixUserId: "12" },
  myUserCode
});

const mustContain = [
  "🤝 <b>ВСТРЕЧИ</b>",
  "🧠 <b>МОИ БЛОКИ РАБОТЫ</b>",
  "🍽 <b>ЛИЧНОЕ</b>",
  "🟢 <b>ОКНО ФОКУСА</b>",
  "➡️ <b>НАЧАТЬ СЕЙЧАС</b>"
];
mustContain.forEach((part) => {
  if (!digest.includes(part)) {
    throw new Error(`calendar_renderer_smoke: missing block ${part}`);
  }
});

console.log("calendar_renderer_smoke_output:");
console.log(digest);
console.log("calendar_renderer_smoke: ok");
EOF_CAL_SMOKE

cat >"$project_path/src/send-digest.mjs" <<'EOF_DIGEST'
import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import {
  buildReplanSuggestion,
  formatExecutiveEvening,
  formatExecutiveMorning,
  suggestDailyScope
} from "./reports/executiveDigestFormatter.mjs";
import {
  alreadySent,
  filterDueToday,
  filterOverdue,
  filterTasksForDate,
  loadDigestState,
  markMatrixSnapshot,
  markSent,
  saveTasksSnapshot
} from "./service.mjs";
import { classifyTasks, splitByQuadrant, suggestExecutionOrder } from "./eisenhower.mjs";
import { dateISOInTz } from "./time.mjs";
import { sendTelegramMessage } from "./telegram.mjs";
import { getAgenda } from "./agenda/aggregate.mjs";
import { formatMorningSecretaryDigest } from "./reports/morningSecretaryDigest.mjs";
import { renderDailyCalendarDigest } from "./reports/calendarDailyRenderer.mjs";
import { buildDayScenarioMessage } from "./execution/timelineBuilder.mjs";
import { getExecutionStatus } from "./execution/executionEngine.mjs";
import { getPersonalizationSnapshot } from "./personal/personalizationEngine.mjs";
import {
  buildFocusProposal,
  createRescheduleSuggestion,
  formatFocusBlocksMessage,
  formatRescheduleSuggestions,
  pickCriticalForReschedule,
  saveFocusProposalForDate
} from "./productivity.mjs";

function moscowHourNow() {
  const hh = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Moscow", hour: "2-digit", hour12: false }).format(new Date());
  return Number(hh);
}

function toPriorityCounts(split) {
  return {
    P1: split.Q1.length,
    P2: split.Q2.length,
    P3: split.Q3.length,
    P4: split.Q4.length
  };
}

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;");
}

function toMyUserCode(cfg) {
  const raw = String(cfg?.bitrixUserId || "").trim();
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

function formatBitrixOnlyMorning({ dateIso, tz, meetings, todoWarning, myUserCode }) {
  const digest = renderDailyCalendarDigest({
    agenda: {
      date: dateIso,
      meetings: meetings || [],
      freeSlots: [],
      tasks: [],
      overdueCount: 0
    },
    cfg: { tz },
    myUserCode
  });
  return `${todoWarning}\n\n${digest}`;
}

function buildTodoWarning(err) {
  const reason = String(err?.message || err || "неизвестная ошибка")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 220);
  return `⚠️ ToDo (Todoist) временно недоступен: ${escapeHtml(reason)}. Отправляю отчет только по встречам Bitrix.`;
}

async function main() {
  const slot = process.argv[2];
  if (!["morning", "evening", "midday"].includes(slot)) {
    throw new Error("Usage: node src/send-digest.mjs <morning|evening|midday>");
  }

  const cfg = getConfig();
  if (!cfg.digestEnabled) {
    console.log("digest_disabled");
    return;
  }

  if (slot === "midday" && !cfg.middayReplanEnabled) {
    console.log("midday_replan_disabled");
    return;
  }

  if (!cfg.telegramBotToken || !cfg.telegramOwnerId) {
    throw new Error("TELEGRAM_BOT_TOKEN or TELEGRAM_OWNER_ID is missing");
  }

  const dateIso = dateISOInTz(new Date(), cfg.tz);
  const state = loadDigestState(cfg.stateDir);
  if (alreadySent(state, dateIso, slot)) {
    console.log(`skip_duplicate slot=${slot} date=${dateIso}`);
    return;
  }

  let tasks = [];
  let todoWarning = "";
  let todoUnavailable = false;

  try {
    const provider = createProvider(cfg);
    tasks = await provider.getAllOpenTasks();
    saveTasksSnapshot(cfg.stateDir, cfg.tz, tasks, cfg);
  } catch (err) {
    if (slot !== "morning") throw err;
    todoUnavailable = true;
    todoWarning = buildTodoWarning(err);
    console.error(`[digest] todo_unavailable slot=${slot} reason=${err?.message || err}`);
  }

  let text = "";
  let extraMessages = [];

  if (slot === "morning") {
    let morningAgenda = null;
    let todayTasks = [];
    let overdue = [];
    let split = { Q1: [], Q2: [], Q3: [], Q4: [] };
    let order = [];

    if (todoUnavailable) {
      morningAgenda = await getAgenda(cfg, dateIso, {
        skipTodoFetch: true,
        todoWarning
      });
    } else {
      todayTasks = filterTasksForDate(tasks, dateIso);
      overdue = filterOverdue(tasks, dateIso);
      const withMatrix = classifyTasks(todayTasks, { todayIso: dateIso, tz: cfg.tz, cfg });
      split = splitByQuadrant(withMatrix);
      order = suggestExecutionOrder(withMatrix);
    }

    if (cfg.morningSecretaryEnabled) {
      if (!morningAgenda) {
        morningAgenda = await getAgenda(cfg, dateIso, { prefetchedTasks: tasks });
      }
      const personalSnapshot = getPersonalizationSnapshot(cfg);
      text = formatMorningSecretaryDigest(morningAgenda, cfg, {
        withHintTomorrow: false,
        personalSnapshot
      });
      if (todoUnavailable) {
        text = `${todoWarning}\n\n${text}`;
      }
    } else if (todoUnavailable) {
      text = formatBitrixOnlyMorning({
        dateIso,
        tz: cfg.tz,
        meetings: morningAgenda?.meetings || [],
        todoWarning,
        myUserCode: toMyUserCode(cfg)
      });
    } else {
      text = formatExecutiveMorning({
        dateIso,
        tasks: todayTasks,
        order,
        overdueCount: overdue.length
      }, { cfg, tz: cfg.tz }).text;
    }

    if (!todoUnavailable) {
      const focusProposal = buildFocusProposal(todayTasks, cfg, dateIso);
      saveFocusProposalForDate(cfg.stateDir, focusProposal);
      if (focusProposal?.blocks?.length) {
        extraMessages.push(formatFocusBlocksMessage(focusProposal.blocks));
      }

      markMatrixSnapshot(cfg.stateDir, {
        date: dateIso,
        slot,
        ...toPriorityCounts(split),
        total: todayTasks.length
      });
    }

    const assistantStatus = getExecutionStatus(cfg, new Date());
    if (cfg.executionModeEnabled && assistantStatus.enabled) {
      if (!morningAgenda) {
        morningAgenda = await getAgenda(cfg, dateIso, {
          prefetchedTasks: todoUnavailable ? [] : tasks,
          skipTodoFetch: todoUnavailable,
          todoWarning
        });
      }
      extraMessages.push(buildDayScenarioMessage(morningAgenda, cfg));
    }
  }

  if (slot === "evening") {
    const overdue = filterOverdue(tasks, dateIso);
    const dueToday = filterDueToday(tasks, dateIso);

    text = formatExecutiveEvening({
      dateIso,
      overdue,
      dueToday
    }, { cfg, tz: cfg.tz }).text + "\n\nКоманда: /day tomorrow";

    const critical = pickCriticalForReschedule([...overdue, ...dueToday]);
    const suggestions = critical.slice(0, 5).map((t) => createRescheduleSuggestion(t, new Date()));
    if (suggestions.length) {
      extraMessages.push(formatRescheduleSuggestions(suggestions));
    }

    const withMatrix = classifyTasks([...overdue, ...dueToday], { todayIso: dateIso, tz: cfg.tz, cfg });
    const split = splitByQuadrant(withMatrix);
    markMatrixSnapshot(cfg.stateDir, {
      date: dateIso,
      slot,
      ...toPriorityCounts(split),
      total: overdue.length + dueToday.length
    });
  }

  if (slot === "midday") {
    const overdue = filterOverdue(tasks, dateIso);
    const dueToday = filterDueToday(tasks, dateIso);
    const todayOpen = [...overdue, ...dueToday];
    const normalizedHour = moscowHourNow();
    const scope = suggestDailyScope(todayOpen, { nowHour: normalizedHour, dayEndHour: 20 });

    if (scope.remaining <= scope.estimatedCapacity) {
      console.log(`midday_skip_balanced remaining=${scope.remaining} cap=${scope.estimatedCapacity}`);
      return;
    }

    text = buildReplanSuggestion(todayOpen, { nowHour: normalizedHour, dayEndHour: 20, tz: cfg.tz }).text;
  }

  const r = await sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, text);
  for (const msg of extraMessages) {
    await sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, msg);
  }
  markSent(cfg.stateDir, dateIso, slot);
  console.log(`sent slot=${slot} date=${dateIso} message_id=${r?.result?.message_id ?? "n/a"} extras=${extraMessages.length}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
EOF_DIGEST

cd "$project_path"
perl -0pi -e 's/import \{ buildDateTimeByDateAndTime, createMeeting, moveMeeting, resolveUserMentions, syncBitrixUsers, usersFind \} from "\.\/agenda\/providers\/bitrixUsers\.mjs";/import { buildDateTimeByDateAndTime, createMeeting, listSections, moveMeeting, resolveUserMentions, setStoredDefaultSectionId, syncBitrixUsers, usersFind } from ".\/agenda\/providers\/bitrixUsers.mjs";/' src/selftest.mjs
perl -0pi -e 's/day\|agenda\|free\|sync_status\|connect_google\|connect_bitrix\|oauth_google\|oauth_bitrix/day|agenda|free|diag|sync_status|connect_google|connect_bitrix|oauth_google|oauth_bitrix/g' src/add-task-flow.mjs
perl -0pi -e 'if ($_ !~ /"\/diag",/) { s/"\/sync_status",/"\/sync_status",\n    "\/diag",/; }' src/formatter.mjs
perl -0pi -e 's@function assertCeoBriefing\(secretaryText\) \{[\s\S]*?\n\}\n\nasync function runReminderSelftest@function assertCeoBriefing(secretaryText) {\n  if (!secretaryText.includes("☀️ <b>")) throw new Error("selftest: missing HTML header");\n  if (!secretaryText.includes("📊 День:")) throw new Error("selftest: missing day summary");\n  if (!secretaryText.includes("🤝 <b>ВСТРЕЧИ</b>")) throw new Error("selftest: missing meetings block");\n  if (!secretaryText.includes("➡️ <b>НАЧАТЬ СЕЙЧАС</b>")) throw new Error("selftest: missing next action block");\n  if (secretaryText.includes("МОЙ РИТМ")) throw new Error("selftest: rhythm block should not be present");\n  if (!secretaryText.includes("────────")) throw new Error("selftest: expected separators");\n  if (secretaryText.length > 2600) throw new Error("selftest: briefing too long for quick read");\n}\n\nasync function runReminderSelftest@s' src/selftest.mjs
perl -0pi -e 's/if \(!secretaryText\.includes\("☀️ "\)\) throw new Error\("selftest: missing morning sun header"\);/if (!secretaryText.includes("☀️ <b>")) throw new Error("selftest: missing HTML header");/g' src/selftest.mjs
perl -0pi -e 's/if \(!secretaryText\.includes\("🎯 ГЛАВНОЕ СЕГОДНЯ"\)\) throw new Error\("selftest: missing main-win block"\);/if (!secretaryText.includes("📊 День:")) throw new Error("selftest: missing day summary");/g' src/selftest.mjs
perl -0pi -e 's@if \(!secretaryText\.includes\("➡️ СЛЕДУЮЩЕЕ ДЕЙСТВИЕ"\)\) throw new Error\("selftest: missing next action block"\);@if (!secretaryText.includes("➡️ <b>НАЧАТЬ СЕЙЧАС</b>")) throw new Error("selftest: missing next action block");@g' src/selftest.mjs
perl -0pi -e 's@if \(!secretaryText\.includes\("🗓 ВСТРЕЧИ"\)\) throw new Error\("selftest: missing meetings block"\);@if (!secretaryText.includes("🤝 <b>ВСТРЕЧИ</b>")) throw new Error("selftest: missing meetings block");@g' src/selftest.mjs
perl -0pi -e 's/if \(!secretaryText\.includes\("⚠️ РИСКИ"\)\) throw new Error\("selftest: missing risks block"\);/if (secretaryText.includes("МОЙ РИТМ")) throw new Error("selftest: rhythm block should not be present");/g' src/selftest.mjs
perl -0pi -e 's@  const meetingPart = secretaryText.split\("🗓 ВСТРЕЧИ"\)\[1\]\?\.split\("━━━━━━━━━━━━"\)\[0\] \|\| "";\n  if \/\^\\s\*•\/m\.test\(meetingPart\) throw new Error\("selftest: meetings should be timeline lines without bullets"\);\n\n@  if (!secretaryText.includes("────────")) throw new Error("selftest: expected separators");\n\n@s' src/selftest.mjs
perl -0pi -e 's@const nextPart = secretaryText.split\("➡️ СЛЕДУЮЩЕЕ ДЕЙСТВИЕ"\)\[1\] \|\| "";@const nextPart = secretaryText.split("➡️ <b>НАЧАТЬ СЕЙЧАС</b>")[1] || "";@g' src/selftest.mjs
perl -0pi -e 's/if \(secretaryText.length > 2500\) throw new Error\("selftest: briefing too long for quick read"\);/if (secretaryText.length > 2600) throw new Error("selftest: briefing too long for quick read");/g' src/selftest.mjs

node --check src/providers/todoist-provider.mjs
node --check src/agenda/aggregate.mjs
node --check src/reports/calendarDailyRenderer.mjs
node --check src/reports/morningSecretaryDigest.mjs
node --check src/agenda-query.mjs
node --check src/send-digest.mjs
node --check src/selftests/calendarDailyRenderer.smoke.mjs
node --check src/selftest.mjs
node src/selftests/calendarDailyRenderer.smoke.mjs

if [ -f "$cron_file" ]; then
  perl -i -pe 'if (/npm run digest:morning/) { s/^\S+\s+\S+\s+\S+\s+\S+\s+\S+ /30 6 * * * /; }' "$cron_file"
  perl -i -pe 's/# 08:00 MSK = 05:00 UTC/# 09:30 MSK = 06:30 UTC/' "$cron_file"
fi

if [ -f /root/.openclaw/openclaw.json ]; then
  current_provider=$(jq -r '.tools.web.search.provider // empty' /root/.openclaw/openclaw.json 2>/dev/null || true)
  current_provider_lc=$(printf '%s' "$current_provider" | tr '[:upper:]' '[:lower:]')
  brave_key_cfg=$(jq -r '.tools.web.search.brave.apiKey // empty' /root/.openclaw/openclaw.json 2>/dev/null || true)
  brave_key_env="${BRAVE_API_KEY:-}"
  if [ -z "$brave_key_env" ] && command -v docker >/dev/null 2>&1 && docker inspect "$container_name" >/dev/null 2>&1; then
    brave_key_env=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container_name" 2>/dev/null | sed -n 's/^BRAVE_API_KEY=//p' | head -n1 || true)
  fi

  target_provider="$current_provider_lc"
  reason=""
  case "$current_provider_lc" in
    duckduckgo)
      ;;
    ddg)
      target_provider="duckduckgo"
      reason="normalize_ddg"
      ;;
    brave)
      if [ -z "$brave_key_cfg" ] && [ -z "$brave_key_env" ]; then
        target_provider="duckduckgo"
        reason="brave_missing_key_fallback_to_duckduckgo"
      fi
      ;;
    perplexity|grok|gemini|kimi)
      ;;
    *)
      target_provider="duckduckgo"
      reason="fallback_to_duckduckgo"
      ;;
  esac

  if [ "$target_provider" = "$current_provider_lc" ]; then
    echo "openclaw_provider_ok=${current_provider_lc:-<empty>}"
  else
    tmp_cfg=$(mktemp)
    jq --arg provider "$target_provider" '
      .tools = (.tools // {}) |
      .tools.web = (.tools.web // {}) |
      .tools.web.search = (.tools.web.search // {}) |
      .tools.web.search.enabled = true |
      .tools.web.search.provider = $provider
    ' /root/.openclaw/openclaw.json >"$tmp_cfg"
    mv "$tmp_cfg" /root/.openclaw/openclaw.json
    echo "openclaw_provider_fixed from=${current_provider_lc:-<empty>} to=${target_provider} reason=${reason:-manual}"
  fi

  # Контейнер читает конфиг под uid=1000; после root-редактирования восстанавливаем права.
  chown 1000:1000 /root/.openclaw/openclaw.json
  chmod 0644 /root/.openclaw/openclaw.json
fi

docker restart "$container_name" >/dev/null
stable=0
stable_restart_count=""
for i in $(seq 1 15); do
  state_line=$(docker inspect --format '{{.State.Status}} {{.State.Restarting}} {{.RestartCount}}' "$container_name" 2>/dev/null || true)
  echo "container_probe_${i}=${state_line}"
  st=$(printf '%s' "$state_line" | awk '{print $1}')
  restarting=$(printf '%s' "$state_line" | awk '{print $2}')
  restart_count=$(printf '%s' "$state_line" | awk '{print $3}')
  if [ "$st" = "running" ] && [ "$restarting" = "false" ]; then
    stable=1
    stable_restart_count="$restart_count"
    break
  fi
  sleep 2
done

if [ "$stable" -ne 1 ]; then
  echo "Контейнер не стабилизировался после фикса."
  docker logs --tail 120 "$container_name" 2>&1 || true
  exit 1
fi

sleep 8
state_after=$(docker inspect --format '{{.State.Status}} {{.State.Restarting}} {{.RestartCount}}' "$container_name" 2>/dev/null || true)
echo "container_probe_after=${state_after}"
st_after=$(printf '%s' "$state_after" | awk '{print $1}')
restarting_after=$(printf '%s' "$state_after" | awk '{print $2}')
restart_after=$(printf '%s' "$state_after" | awk '{print $3}')
if [ "$st_after" != "running" ] || [ "$restarting_after" != "false" ] || [ "$restart_after" != "$stable_restart_count" ]; then
  echo "Контейнер нестабилен после задержки (restart_count изменился или статус не running)."
  docker logs --tail 120 "$container_name" 2>&1 || true
  exit 1
fi

echo '--- Morning cron line ---'
grep -n 'digest:morning' "$cron_file" || true
echo "backup_dir=$backup_dir"
