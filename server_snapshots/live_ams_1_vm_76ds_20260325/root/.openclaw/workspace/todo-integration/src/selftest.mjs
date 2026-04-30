import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import { parseAddDraft } from "./add-parser.mjs";
import { addDaysISO, dateISOInTz } from "./time.mjs";
import { parseVoiceTasks } from "./voice-tasks.mjs";
import { detectPriority } from "./priority.mjs";
import { buildReplanSuggestion, formatExecutiveEvening, formatExecutiveMorning } from "./reports/executiveDigestFormatter.mjs";
import { runRemindersTick } from "./reminders.mjs";
import {
  acceptFocusProposal,
  buildFocusProposal,
  clearRescheduleConfirm,
  queueRescheduleConfirm,
  saveFocusProposalForDate,
  saveRescheduleRecord,
  setDnd,
  setDndWindow
} from "./productivity.mjs";
import { loadFocusBlocks, loadTaskReschedules } from "./productivity-state.mjs";
import { runFocusTick } from "./focus-tick.mjs";
import { fetchGoogleAgendaForDate, googleConnected } from "./agenda/providers/googleCalendar.mjs";
import { bitrixConnected, fetchBitrixAgendaForDate, bitrixPing } from "./agenda/providers/bitrixCalendar.mjs";
import { buildDateTimeByDateAndTime, createMeeting, listSections, moveMeeting, resolveUserMentions, setStoredDefaultSectionId, syncBitrixUsers, usersFind } from "./agenda/providers/bitrixUsers.mjs";
import { getAgenda } from "./agenda/aggregate.mjs";
import { formatMorningSecretaryDigest, formatMeetingLine } from "./reports/morningSecretaryDigest.mjs";
import { buildDayScenarioMessage } from "./execution/timelineBuilder.mjs";
import { getExecutionStatus, runExecutionTick, setExecutionEnabled } from "./execution/executionEngine.mjs";
import { buildRhythmModel } from "./personal/rhythmModel.mjs";
import { adaptNextActionByRhythm, getPersonalizationSnapshot } from "./personal/personalizationEngine.mjs";
import { formatMeInsights } from "./personal/insightsFormatter.mjs";
import { insertAssistantEvent, insertTaskEvent, setProfileEnabled, wipeTelemetry, queryAll } from "./personal/storage.mjs";

function sample(items, n = 3) {
  return items.slice(0, n).map((t) => ({ content: t.content, due: t.dueDateTime || t.dueDate || null }));
}

function runParserTests(tz) {
  const phrases = [
    "добавь задачу позвонить клиенту завтра",
    "задача: отправить КП 2026-03-01",
    "поставь на пятницу 10:30 созвон с Пашей",
    "добавь: оплатить хостинг",
    "todo: купить кофе послезавтра",
    "напомни через 3 дня оплатить налоги",
    "поставь задачу на завтра позвонить ольге в туду лист"
  ];

  console.log("parser_tests:");
  for (const phrase of phrases) {
    const d = parseAddDraft(phrase, tz);
    console.log(JSON.stringify({ input: phrase, content: d.content, dueDate: d.dueDate, dueDateTime: d.dueDateTime, needDateClarify: d.needDateClarify }));
  }
}

function runVoiceMockTest(cfg) {
  const mock = "Так, добавить задачу срочно позвонить клиенту завтра, потом отправить КП в пятницу, и еще когда будет время оплатить хостинг";
  const parsed = parseVoiceTasks(mock, cfg.tz, cfg.voiceMaxTasks);
  const tasks = parsed.tasks.map((t) => {
    const p = detectPriority(t.content, cfg);
    return {
      content: p.content,
      dueDate: t.dueDate,
      dueDateTime: t.dueDateTime,
      priority: p.priority,
      confidence: Number(p.confidence.toFixed(2))
    };
  });

  console.log("voice_mock_input:", mock);
  console.log("voice_mock_tasks:", JSON.stringify(tasks, null, 2));
  return tasks;
}

function buildMockDay(todayIso) {
  return [
    { id: "1", content: "[CRM сделка](https://belberrycrm.bitrix24.ru/company/personal/user/12/tasks/task/view/365576/?any=user%2F12%2Ftasks%2Ftask%2Fview%2F365576%2F)", dueDate: todayIso, priority: 4, completed: false },
    { id: "2", content: "срочно отправить договор", dueDate: todayIso, priority: 4, completed: false },
    { id: "3", content: "подготовить отчет по KPI", dueDate: todayIso, priority: 3, completed: false },
    { id: "4", content: "дубли лидов", dueDate: todayIso, priority: 3, completed: false },
    { id: "5", content: "проверить CRM", dueDate: todayIso, priority: 2, completed: false },
    { id: "6", content: "ответить на письмо", dueDate: todayIso, priority: 2, completed: false },
    { id: "7", content: "Google sheet сверка", dueDate: todayIso, priority: 2, completed: false },
    { id: "8", content: "когда будет время почитать статью", dueDate: null, priority: 1, completed: false },
    { id: "9", content: "https://docs.google.com/spreadsheets/d/1ZxONfLBWDuPSyBx_FnXyoIJKBlXd1ebisRjMMvrkM8o/edit?gid=0#gid=0", dueDate: todayIso, priority: 3, completed: false },
    { id: "10", content: "срочно отправить договор", dueDate: todayIso, priority: 4, completed: false }
  ];
}

function assertExecutiveDigest(morning, evening, replan) {
  if (!morning.text.includes("🎯 Фокус дня")) throw new Error("selftest: missing focus block");
  if (/\bQ[1-4]\b/.test(morning.text + "\n" + evening.text + "\n" + replan.text)) throw new Error("selftest: found Q1/Q2/Q3/Q4 in text");
  const longUrl = (morning.text + "\n" + evening.text).match(/https?:\/\/\S{120,}/);
  if (longUrl) throw new Error("selftest: long URL leaked in digest");
  if (!morning.text.includes("ещё ") || !morning.text.includes("/tasks full")) throw new Error("selftest: pruning marker missing");
}

function assertMeetingLineFormatting(cfg) {
  const base = {
    title: "Тестовая встреча",
    start: "2026-02-27T10:00:00+03:00",
    end: "2026-02-27T11:00:00+03:00",
    attendees: []
  };

  const noPeople = formatMeetingLine(base, cfg);
  if (noPeople.includes("(с:")) throw new Error("selftest: unexpected attendees block for empty list");
  if (noPeople.includes("()")) throw new Error("selftest: empty brackets in meeting line");

  const allDay = formatMeetingLine({ ...base, isAllDay: true }, cfg);
  if (!allDay.startsWith("Весь день")) throw new Error("selftest: all-day format broken");

  const longPeople = formatMeetingLine({
    ...base,
    attendees: ["Иван", "Пётр", "Мария", "Олег", "Анна", "Елена"]
  }, cfg);
  if (!longPeople.includes("+ ещё 1")) throw new Error("selftest: long attendees list was not shortened");
}

function assertCeoBriefing(secretaryText) {
  if (!secretaryText.includes("☀️ <b>")) throw new Error("selftest: missing HTML header");
  if (!secretaryText.includes("📊 День:")) throw new Error("selftest: missing day summary");
  if (!secretaryText.includes("➡️ <b>НАЧАТЬ СЕЙЧАС</b>")) throw new Error("selftest: missing next action block");
  if (!secretaryText.includes("🤝 <b>ВСТРЕЧИ</b>") && !secretaryText.includes("День: 0 встреч")) throw new Error("selftest: missing meetings block");
  if (secretaryText.includes("МОЙ РИТМ")) throw new Error("selftest: rhythm block should not be present");

  const meetingPart = secretaryText.split("🗓 ВСТРЕЧИ")[1]?.split("━━━━━━━━━━━━")[0] || "";
  if (/^\s*•/m.test(meetingPart)) throw new Error("selftest: meetings should be timeline lines without bullets");

  const nextPart = secretaryText.split("➡️ <b>НАЧАТЬ СЕЙЧАС</b>")[1] || "";
  const nextLines = nextPart.split(/\n/).map((x) => x.trim()).filter(Boolean);
  if (!nextLines.length) throw new Error("selftest: next action text is empty");
  if (nextLines.length > 2) throw new Error("selftest: next action must be concise");

  if (secretaryText.length > 2600) throw new Error("selftest: briefing too long for quick read");
}


async function runReminderSelftest(cfg) {
  const stateDir = path.join(os.tmpdir(), `todo-reminder-selftest-${Date.now()}`);
  fs.mkdirSync(stateDir, { recursive: true });
  setDndWindow(stateDir, "00:00", "23:59");
  setDnd(stateDir, true);

  const base = Date.now();
  const dueSoon = new Date(base + 2 * 60 * 1000).toISOString();

  const provider = {
    async getAllOpenTasks() {
      return [
        { id: "allow", content: "Критичный созвон", dueDateTime: dueSoon, completed: false, priority: 4, url: "https://example.com/a" },
        { id: "suppress", content: "Рутинная задача", dueDateTime: dueSoon, completed: false, priority: 2, url: "https://example.com/s" }
      ];
    }
  };

  const sent = [];
  const sendFn = async (text, replyMarkup) => {
    sent.push({ text, hasButton: !!replyMarkup });
  };

  const baseCfg = {
    ...cfg,
    stateDir,
    taskReminderPreMin: 1,
    taskReminderFollowupMin: 1,
    reminderStyle: "normal",
    remindersEnabledDefault: true,
    provider,
    sendFn,
    dndEnabled: true,
    dndNightStart: "00:00",
    dndNightEnd: "23:59"
  };

  const r1 = await runRemindersTick({ ...baseCfg, nowMs: base + 61 * 1000 });
  const r2 = await runRemindersTick({ ...baseCfg, nowMs: base + 121 * 1000 });
  const r3 = await runRemindersTick({ ...baseCfg, nowMs: base + 181 * 1000 });

  if ((r1.sent.suppressed + r2.sent.suppressed + r3.sent.suppressed) < 1) {
    throw new Error("selftest: expected suppressed notifications in DND");
  }

  setDnd(stateDir, false);
  await runRemindersTick({ ...baseCfg, nowMs: base + 240 * 1000, provider: { async getAllOpenTasks() { return []; } } });

  const hadSummary = sent.some((x) => x.text.includes("Пока был DND, пропущено:"));
  if (!hadSummary) throw new Error("selftest: suppressed summary not flushed after DND");

  console.log("reminders_log:\n" + sent.map((x) => x.text).join("\n---\n"));
}

async function runProductivitySelftest(cfg, todayIso) {
  const stateDir = path.join(os.tmpdir(), `todo-productivity-selftest-${Date.now()}`);
  fs.mkdirSync(stateDir, { recursive: true });

  const focusTasks = [
    { id: "f1", content: "Подготовить договор", priority: 4, dueDate: todayIso },
    { id: "f2", content: "Созвон с клиентом", priority: 3, dueDate: todayIso },
    { id: "f3", content: "Обновить CRM", priority: 3, dueDate: todayIso }
  ];

  const p = buildFocusProposal(focusTasks, { ...cfg, tz: "Europe/Moscow" }, todayIso);
  if (!p?.blocks?.length) throw new Error("selftest: focus proposal not created");
  saveFocusProposalForDate(stateDir, p);
  const accepted = acceptFocusProposal(stateDir, todayIso);
  if (!accepted.ok) throw new Error("selftest: focus accept failed");

  const sent = [];
  const sendFn = async (text) => sent.push(text);
  const preTs = new Date(`${todayIso}T06:55:00Z`).getTime();
  const startTs = new Date(`${todayIso}T07:00:00Z`).getTime();
  const endTs = new Date(`${todayIso}T08:05:00Z`).getTime();

  await runFocusTick({ ...cfg, stateDir, nowMs: preTs, sendFn, focusPreNotifyMin: 5, tz: "Europe/Moscow" });
  await runFocusTick({ ...cfg, stateDir, nowMs: startTs, sendFn, focusPreNotifyMin: 5, tz: "Europe/Moscow" });
  await runFocusTick({ ...cfg, stateDir, nowMs: endTs, sendFn, focusPreNotifyMin: 5, tz: "Europe/Moscow" });

  if (sent.length < 3) throw new Error("selftest: focus lifecycle messages missing");

  const before = loadTaskReschedules(stateDir).entries.length;
  queueRescheduleConfirm(stateDir, "u1", { task_id: "123", planned_due_datetime: `${todayIso}T10:00:00+03:00`, source: "user" });
  const stillBefore = loadTaskReschedules(stateDir).entries.length;
  if (before !== stillBefore) throw new Error("selftest: reschedule changed without confirmation");
  saveRescheduleRecord(stateDir, { task_id: "123", planned_due_datetime: `${todayIso}T10:00:00+03:00`, source: "user", apply_mode: "local" });
  clearRescheduleConfirm(stateDir, "u1");
  const after = loadTaskReschedules(stateDir).entries.length;
  if (after !== before + 1) throw new Error("selftest: reschedule confirmation flow failed");

  const blocks = loadFocusBlocks(stateDir).entries;
  console.log("focus_blocks_preview:", JSON.stringify(blocks.slice(0, 2), null, 2));
  console.log("focus_tick_messages:\n" + sent.join("\n---\n"));
}

async function runCreateTest(cfg, provider, todayIso, voiceTasks) {
  const tomorrowIso = addDaysISO(todayIso, 1);
  const payload = {
    content: `TEST_selftest_${new Date().toISOString()}`,
    dueDate: tomorrowIso,
    dueDateTime: null,
    dueString: null,
    priority: 2
  };

  if (cfg.todoDryRun) {
    console.log(`create_test_single: dry_run=1 payload=${JSON.stringify(payload)}`);
    return;
  }

  const created = await provider.createTask(payload);
  console.log(`create_test_single: created id=${created.id || ""} url=${created.url || ""}`);
  if (voiceTasks.length) console.log(`voice_pipeline_mock_count=${voiceTasks.length}`);
}

async function main() {
  const cfg = getConfig();
  const missing = [];
  if (!cfg.todoToken) missing.push("TODO_TOKEN");
  if (!cfg.telegramOwnerId) missing.push("TELEGRAM_OWNER_ID");
  if (missing.length) {
    console.error(`selftest: missing env: ${missing.join(", ")}`);
    process.exit(1);
  }

  const todayIso = dateISOInTz(new Date(), cfg.tz);
  console.log(`timezone_check: tz=${cfg.tz} today=${todayIso}`);

  runParserTests(cfg.tz);
  const voiceTasks = runVoiceMockTest(cfg);

  const mockTasks = buildMockDay(todayIso);
  const digestCfg = {
    ...cfg,
    digestShowPriorityBlock: true,
    digestMaxVisibleTasks: 5,
    digestMaxTasksPerSection: 3,
    digestMaxTotalTasks: 20,
    digestShortLinkBase: cfg.digestShortLinkBase || "https://example.local"
  };

  const morning = formatExecutiveMorning({ dateIso: todayIso, tasks: mockTasks, order: mockTasks, overdueCount: 1 }, { cfg: digestCfg, tz: cfg.tz });
  const evening = formatExecutiveEvening({ dateIso: todayIso, overdue: mockTasks.slice(0, 2), dueToday: mockTasks.slice(2, 8) }, { cfg: digestCfg, tz: cfg.tz });
  const replan = buildReplanSuggestion(mockTasks, { tz: cfg.tz, nowHour: 14, dayEndHour: 20 });

  console.log("digest_morning_preview:\n" + morning.text);
  console.log("digest_evening_preview:\n" + evening.text);
  console.log("replan_preview:\n" + replan.text);
  assertExecutiveDigest(morning, evening, replan);
  assertMeetingLineFormatting(cfg);

  await runReminderSelftest(cfg);
  await runProductivitySelftest(cfg, todayIso);
  await runExecutionSelftest(cfg, todayIso);
  await runPersonalizationSelftest(cfg, todayIso);

  const provider = createProvider(cfg);
  const todayTasks = await provider.getTasksForDate(todayIso);
  const overdueToday = await provider.getOverdueAndToday(todayIso);

  console.log(`tasks_today_count=${todayTasks.length}`);
  console.log(`overdue_plus_today_count=${overdueToday.length}`);
  console.log("sample_today:", JSON.stringify(sample(todayTasks), null, 2));
  console.log("sample_overdue_today:", JSON.stringify(sample(overdueToday), null, 2));

  let googleOk = false;
  let bitrixOk = false;

  if (await googleConnected(cfg)) {
    const g = await fetchGoogleAgendaForDate(cfg, todayIso);
    googleOk = true;
    console.log(`google_events_today=${g.length}`);
    console.log("google_sample:", JSON.stringify(g.slice(0, 2), null, 2));
  } else {
    console.log("google_events_today=not_connected");
  }

  if (await bitrixConnected(cfg)) {
    const ping = await bitrixPing(cfg);
    console.log(`bitrix_ping=${JSON.stringify(ping)}`);

    const usersSync = await syncBitrixUsers(cfg, { force: true });
    if (!usersSync.ok) throw new Error(`selftest: bitrix users sync failed: ${usersSync.error || "unknown"}`);
    console.log(`bitrix_users_sync active=${usersSync.count}`);

    if (!cfg.bitrixDefaultSectionId) {
      const secs = await listSections(cfg);
      if (secs.length) setStoredDefaultSectionId(cfg.stateDir, secs[0].id);
    }

    const testName = cfg.testInviteeName || "Денис";
    const foundUsers = await usersFind(cfg, testName, 10);
    console.log(`bitrix_users_find_${testName}=${foundUsers.length}`);
    if (!foundUsers.length) throw new Error(`selftest: no matches for TEST_INVITEE_NAME='${testName}'`);

    const resolved = await resolveUserMentions(cfg, [testName]);
    if (!resolved.resolved.length) throw new Error("selftest: resolveUserMentions failed");

    const startIso = buildDateTimeByDateAndTime(todayIso, "23:45");
    const endIso = new Date(new Date(startIso).getTime() + 15 * 60000).toISOString().replace(".000Z", "+03:00");
    const dry = await createMeeting(cfg, {
      title: `TEST_DRY_${Date.now()}`,
      startIso,
      endIso,
      attendeesCodes: [`U${resolved.resolved[0].userId}`]
    }, { dryRun: true });
    console.log("bitrix_meeting_dry_payload:", JSON.stringify(dry.fields, null, 2));

    if (!cfg.bitrixCalendarDryRun) {
      const created = await createMeeting(cfg, {
        title: `TEST_LIVE_${Date.now()}`,
        startIso,
        endIso,
        attendeesCodes: [`U${resolved.resolved[0].userId}`]
      }, { dryRun: false });
      if (!created.readback?.isMeeting) throw new Error("selftest: created meeting readback invalid");
      const movedStart = new Date(new Date(startIso).getTime() + 15 * 60000).toISOString().replace(".000Z", "+03:00");
      const movedEnd = new Date(new Date(endIso).getTime() + 15 * 60000).toISOString().replace(".000Z", "+03:00");
      await moveMeeting(cfg, created.eventId, movedStart, movedEnd, { dryRun: false });
      console.log(`bitrix_meeting_live_ok id=${created.eventId}`);
    }

    const b = await fetchBitrixAgendaForDate(cfg, todayIso);
    bitrixOk = true;
    console.log(`bitrix_events_today=${b.length}`);
    console.log("bitrix_sample:", JSON.stringify(b.slice(0, 2), null, 2));

    const attendeesPreview = b.slice(0, 3).map((e) => ({
      id: e.id,
      raw_attendees_ids: e.attendeeIds || [],
      resolved_attendees: e.attendees || [],
      line: formatMeetingLine(e, cfg)
    }));
    console.log("bitrix_attendees_preview:", JSON.stringify(attendeesPreview, null, 2));

    const ownerId = String(cfg.bitrixUserId || "").trim();
    const ownerLeak = b.some((e) => (e.attendeeIds || []).includes(ownerId));
    if (ownerLeak) throw new Error("selftest: owner was not excluded from attendees");

    const hasEmptyBrackets = attendeesPreview.some((x) => /\(с:\s*\)/.test(x.line));
    if (hasEmptyBrackets) throw new Error("selftest: empty attendees brackets found");
  } else {
    console.log("bitrix_events_today=not_connected");
  }

  const agenda = await getAgenda(cfg, todayIso);
  const sec = formatMorningSecretaryDigest(agenda, cfg, { withHintTomorrow: true });
  console.log("secretary_digest_preview:\n" + sec);
  assertCeoBriefing(sec);

  await runCreateTest(cfg, provider, todayIso, voiceTasks);

  if (!(todayTasks.length >= 0 && (googleOk || bitrixOk))) {
    throw new Error("selftest: calendars unavailable (need at least one calendar + tasks)");
  }

  console.log("selftest: ok");
}

main().catch((err) => {
  console.error(`selftest: fail: ${err.message || err}`);
  process.exit(1);
});

async function runExecutionSelftest(cfg, todayIso) {
  const stateDir = path.join(os.tmpdir(), `todo-execution-selftest-${Date.now()}`);
  fs.mkdirSync(stateDir, { recursive: true });
  setExecutionEnabled(stateDir, true);

  const agenda = {
    date: todayIso,
    meetings: [
      { id: "m1", source: "bitrix", title: "Созвон с клиентом", start: `${todayIso}T10:00:00+03:00`, end: `${todayIso}T10:30:00+03:00`, attendees: ["Иван Петров"] },
      { id: "m2", source: "bitrix", title: "Планерка", start: `${todayIso}T12:00:00+03:00`, end: `${todayIso}T13:00:00+03:00`, attendees: ["Анна", "Роман"] },
      { id: "m3", source: "bitrix", title: "Демо", start: `${todayIso}T17:00:00+03:00`, end: `${todayIso}T17:30:00+03:00`, attendees: ["Олег"] }
    ],
    tasks: [
      { id: "t1", content: "Подготовить договор", dueDate: todayIso, priority: 4, completed: false },
      { id: "t2", content: "Сверить оплату", dueDate: todayIso, priority: 3, completed: false },
      { id: "t3", content: "Ответить клиенту", dueDate: todayIso, priority: 2, completed: false },
      { id: "t4", content: "Проверить CRM", dueDate: todayIso, priority: 2, completed: false },
      { id: "t5", content: "Когда будет время почитать заметки", dueDate: null, priority: 1, completed: false }
    ],
    freeSlots: [
      { start: "09:00", end: "10:00" },
      { start: "10:30", end: "12:00" },
      { start: "13:00", end: "17:00" },
      { start: "17:30", end: "19:00" }
    ]
  };

  const scenario = buildDayScenarioMessage(agenda, { ...cfg, workdayStart: "09:00", workdayEnd: "19:00" });
  if (!scenario.includes("🧭 Сценарий дня")) throw new Error("selftest: execution scenario block missing");

  const sent = [];
  const sendFn = async (text) => sent.push(text);
  const baseCfg = {
    ...cfg,
    stateDir,
    tz: "Europe/Moscow",
    executionModeEnabled: true,
    executionCheckMinutes: 15,
    executionCooldownMinutes: 60,
    executionPreMeetingMin: 10,
    executionPostMeetingMin: 5,
    sendFn,
    agenda
  };

  const tPre = new Date(`${todayIso}T06:50:00Z`).getTime();
  const tPost = new Date(`${todayIso}T07:35:00Z`).getTime();
  const tDeep = new Date(`${todayIso}T11:10:00Z`).getTime();
  const tCooldown = new Date(`${todayIso}T11:25:00Z`).getTime();

  const r1 = await runExecutionTick({ ...baseCfg, nowMs: tPre });
  const r2 = await runExecutionTick({ ...baseCfg, nowMs: tPost });
  const r3 = await runExecutionTick({ ...baseCfg, nowMs: tDeep });
  const r4 = await runExecutionTick({ ...baseCfg, nowMs: tCooldown });

  if (r1.sentType !== "pre_meeting") throw new Error("selftest: missing pre-meeting notification");
  if (r2.sentType !== "post_meeting") throw new Error("selftest: missing post-meeting suggestion");
  if (r3.sentType !== "next_action") throw new Error("selftest: missing deep-work next action");
  if (r4.sent) throw new Error("selftest: cooldown did not prevent spam");

  const status = getExecutionStatus(baseCfg, new Date(tCooldown));
  if (!status.enabled) throw new Error("selftest: assistant status expected enabled");

  console.log("execution_scenario_preview:\n" + scenario);
  console.log("execution_messages:\n" + sent.join("\n---\n"));
}


async function runPersonalizationSelftest(cfg, todayIso) {
  const stateDir = path.join(os.tmpdir(), `todo-personal-selftest-${Date.now()}`);
  fs.mkdirSync(stateDir, { recursive: true });
  setProfileEnabled(stateDir, true);

  // 30-day synthetic behavior: strong 09-11, weak 14-15
  for (let d = 1; d <= 30; d += 1) {
    const day = new Date(Date.now() - d * 24 * 3600 * 1000);
    const iso = dateISOInTz(day, "Europe/Moscow");

    const strongHours = ["09:10", "10:20", "11:15"];
    for (let i = 0; i < strongHours.length; i += 1) {
      insertTaskEvent(stateDir, {
        task_id: `done_${d}_${i}`,
        ts: `${iso}T${strongHours[i]}:00+03:00`,
        event_type: "completed",
        priority: i === 0 ? 1 : 2,
        source: "mock"
      });
    }

    insertTaskEvent(stateDir, {
      task_id: `done_quick_${d}`,
      ts: `${iso}T17:20:00+03:00`,
      event_type: "completed",
      priority: 3,
      source: "mock"
    });

    // tiny recovery before weak hour to anchor weak window at 14:00–15:00
    insertTaskEvent(stateDir, {
      task_id: `done_13_${d}`,
      ts: `${iso}T13:35:00+03:00`,
      event_type: "completed",
      priority: 4,
      source: "mock"
    });

    // weak window: mostly ignored nudges, without completed tasks
    insertAssistantEvent(stateDir, {
      ts: `${iso}T14:10:00+03:00`,
      event_type: "suggestion_sent",
      context: "deep_work",
      payload_json: { source: "selftest" }
    });
    insertAssistantEvent(stateDir, {
      ts: `${iso}T14:12:00+03:00`,
      event_type: "suggestion_ignored",
      context: "deep_work",
      payload_json: { source: "selftest" }
    });
  }

  const cfgP = { ...cfg, stateDir };
  const model = buildRhythmModel(cfgP, { days: 30, minDays: 7 });
  if (!model.enoughData) throw new Error("selftest: personalization model should have enough data");
  if (!String(model.strongWindow || "").startsWith("09:00")) {
    throw new Error(`selftest: expected strong window near 09:00, got ${model.strongWindow || "n/a"}`);
  }
  if (!String(model.weakWindow || "").startsWith("14:00")) {
    throw new Error(`selftest: expected weak window near 14:00, got ${model.weakWindow || "n/a"}`);
  }

  const context = {
    nowHHMM: "10:00",
    tasks: [
      { id: "a", title: "Глубокая задача", displayPriority: 1, etaMin: 70 },
      { id: "b", title: "Быстрый звонок", displayPriority: 3, etaMin: 20 }
    ]
  };

  const baseAction = { kind: "next_action", task: context.tasks[1], key: "k", text: "x" };
  const adapted10 = adaptNextActionByRhythm(baseAction, { ...context, nowHHMM: "10:00" }, model);
  const adapted1430 = adaptNextActionByRhythm(baseAction, { ...context, nowHHMM: "14:30" }, model);

  const meText = formatMeInsights(cfgP);
  if (!meText.includes("Топ-окна")) throw new Error("selftest: /me insights missing expected content");

  const beforeWipe = queryAll(stateDir, "SELECT COUNT(*) AS c FROM task_events")[0]?.c || 0;
  if (!beforeWipe) throw new Error("selftest: mock telemetry not inserted");
  wipeTelemetry(stateDir);
  const afterWipe = queryAll(stateDir, "SELECT COUNT(*) AS c FROM task_events")[0]?.c || 0;
  if (afterWipe !== 0) throw new Error("selftest: profile wipe failed");

  console.log(`personal_top_windows strong=${model.strongWindow} quick=${model.quickWindow} weak=${model.weakWindow}`);
  console.log(`personal_next_action_10_00=${adapted10.task?.title || adapted10.task?.content || "n/a"}`);
  console.log(`personal_next_action_14_30=${adapted1430.task?.title || adapted1430.task?.content || "n/a"}`);
}
