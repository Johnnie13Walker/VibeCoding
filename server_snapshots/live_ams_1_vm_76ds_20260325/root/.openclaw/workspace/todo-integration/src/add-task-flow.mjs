import { getConfig } from "./config.mjs";
import { createProvider } from "./provider-factory.mjs";
import { detectAddIntent, parseAddDraft } from "./add-parser.mjs";
import { looksLikeVoiceBatch, parseVoiceTasks } from "./voice-tasks.mjs";
import { clearPending, getPending, setPending } from "./pending-state.mjs";
import {
  detectPriority,
  parsePriorityOverride,
  priorityHelpText,
  priorityLabel,
  priorityToTodoist
} from "./priority.mjs";
import { getRemindersStatus, setRemindersEnabled } from "./reminders.mjs";
import {
  acceptFocusProposal,
  cancelFocusBlocks,
  clearRescheduleConfirm,
  editFocusBlocks,
  formatFocusBlocksMessage,
  getDndStatus,
  getFocusProposal,
  getRescheduleConfirm,
  queueRescheduleConfirm,
  saveRescheduleRecord,
  setDnd,
  setDndWindow
} from "./productivity.mjs";
import { loadFocusBlocks } from "./productivity-state.mjs";
import { dateISOInTz } from "./time.mjs";
import { runAgendaCommand } from "./agenda-query.mjs";
import { handleMeetingFlow } from "./meeting-flow.mjs";
import { getExecutionStatus, setExecutionEnabled } from "./execution/executionEngine.mjs";
import { formatMeInsights } from "./personal/insightsFormatter.mjs";
import {
  clearProfileWipePending,
  getProfileWipePending,
  isProfileEnabled,
  setProfileEnabled,
  setProfileWipePending,
  wipeTelemetry
} from "./personal/storage.mjs";
import { inferAssistantReactionFromMessage, recordAssistantEvent, recordTaskCreateTelemetry } from "./personal/telemetryCollector.mjs";

function parseArgs() {
  const args = process.argv.slice(2);
  const out = { userId: "", text: "" };
  for (let i = 0; i < args.length; i += 1) {
    const a = args[i];
    if (a === "--user") out.userId = args[i + 1] || "";
    if (a === "--text") out.text = args[i + 1] || "";
  }
  return out;
}

function isYes(text) {
  return /^(да|ок|окей|yes|y|ага|подтверждаю)$/i.test(text.trim());
}

function isNo(text) {
  return /^(нет|no|n|отмена|cancel)$/i.test(text.trim());
}

function isNoDate(text) {
  return /(без\s*даты|без\s*срока|без\s*дедлайна)/i.test(text);
}

function isResolveEach(text) {
  return /^(по\s*одной|по\s*задачам|каждой|для\s*каждой)$/i.test(text.trim());
}

function humanDue(task) {
  if (task.dueDateTime) {
    const [d, t] = task.dueDateTime.split("T");
    return `${d} ${t.slice(0, 5)} (МСК)`;
  }
  if (task.dueDate) return `${task.dueDate} (весь день)`;
  return "без срока";
}

function priorityQuestion() {
  return [
    "Какой приоритет поставить?",
    "1 — 🔥 срочно",
    "2 — ⚡ высокий",
    "3 — обычный",
    "4 — низкий"
  ].join("\n");
}

function parsePriorityAnswer(text) {
  const manual = parsePriorityOverride(text);
  if (manual) return manual;
  const t = text.trim();
  if (/^1$/.test(t)) return "P1";
  if (/^2$/.test(t)) return "P2";
  if (/^3$/.test(t)) return "P3";
  if (/^4$/.test(t)) return "P4";
  return null;
}

function extractNumericIds(raw) {
  const ids = String(raw || "").match(/-?\d+/g);
  return ids ? ids.map((x) => x.trim()).filter(Boolean) : [];
}

function isOwnerUser(userId, ownerId) {
  const uid = String(userId || "").trim();
  const oid = String(ownerId || "").trim();
  if (!uid || !oid) return false;
  if (uid === oid) return true;

  const ownerNums = new Set(extractNumericIds(oid));
  if (!ownerNums.size) return false;
  const userNums = extractNumericIds(uid);
  return userNums.some((n) => ownerNums.has(n));
}

function applyPriority(task, p) {
  task.priority = p;
  task.todoistPriority = priorityToTodoist(p);
  task.priorityConfidence = task.priorityConfidence ?? 1;
}

function previewText(pending) {
  return [
    "Добавляю задачу:",
    `Текст: ${pending.content}`,
    `Срок: ${humanDue(pending)}`,
    `Приоритет: ${priorityLabel(pending.priority || "P3")}`,
    "Ок? (да/нет)"
  ].join("\n");
}

function voicePreviewText(pending) {
  const lines = [
    "Я услышал:",
    pending.transcript || "(пусто)",
    "",
    `Нашёл ${pending.tasks.length} задач:`
  ];

  pending.tasks.slice(0, 30).forEach((task, idx) => {
    lines.push(`${idx + 1}. ${task.content} — ${humanDue(task)} — ${priorityLabel(task.priority || "P3")}`);
  });

  if (pending.lowConfidence) {
    lines.push("");
    lines.push("Я не уверен в распознавании, проверь список.");
  }

  lines.push("");
  lines.push("Продолжить добавление? (да/нет)");
  return lines.join("\n");
}

function parseDateChoice(text, tz) {
  if (isNoDate(text)) {
    return { ok: true, dueDate: null, dueDateTime: null };
  }
  const draft = parseAddDraft(text, tz);
  if (draft.dueDateTime) return { ok: true, dueDate: null, dueDateTime: draft.dueDateTime };
  if (draft.dueDate) return { ok: true, dueDate: draft.dueDate, dueDateTime: null };
  return { ok: false };
}

function applyDateResolution(task, dateChoice) {
  if (!dateChoice.dueDate && !dateChoice.dueDateTime) {
    task.dueDate = null;
    task.dueDateTime = null;
    task.pendingTime = null;
    return;
  }

  if (dateChoice.dueDateTime) {
    task.dueDate = null;
    task.dueDateTime = dateChoice.dueDateTime;
    task.pendingTime = null;
    return;
  }

  if (task.pendingTime) {
    task.dueDate = null;
    task.dueDateTime = `${dateChoice.dueDate}T${task.pendingTime}:00+03:00`;
    task.pendingTime = null;
    return;
  }

  task.dueDate = dateChoice.dueDate;
  task.dueDateTime = null;
  task.pendingTime = null;
}

async function createTaskOrDryRun(cfg, task, source = "text") {
  const payload = {
    content: task.content,
    dueDate: task.dueDate || null,
    dueDateTime: task.dueDateTime || null,
    dueString: null,
    priority: task.todoistPriority || 2
  };

  if (cfg.todoDryRun) {
    return { ok: true, dryRun: true, message: `DRY_RUN ✅ ${JSON.stringify(payload)}` };
  }

  const provider = createProvider(cfg);
  const created = await provider.createTask(payload);
  try {
    recordTaskCreateTelemetry(cfg, { ...task, id: created?.id || task.id }, source);
  } catch {}
  return { ok: true, dryRun: false, created };
}

async function createBatch(cfg, tasks) {
  let added = 0;
  let failed = 0;
  const details = [];

  for (const task of tasks) {
    try {
      await createTaskOrDryRun(cfg, task, task.source || "batch");
      added += 1;
    } catch (err) {
      failed += 1;
      details.push(`${task.content}: ${err.message || err}`);
    }
  }

  let text = `Добавлено: ${added}\nОшибок: ${failed}`;
  if (cfg.todoDryRun) text = `DRY_RUN ✅\n${text}`;
  if (details.length) text += `\n\n${details.slice(0, 3).join("\n")}`;
  return text;
}

function finalizeWithDateReply(basePending, replyDraft) {
  if (!replyDraft.dueDate && !replyDraft.dueDateTime) return null;
  const out = { ...basePending };

  if (basePending.pendingTime && replyDraft.dueDate && !replyDraft.dueDateTime) {
    out.dueDateTime = `${replyDraft.dueDate}T${basePending.pendingTime}:00+03:00`;
    out.dueDate = null;
  } else {
    out.dueDate = replyDraft.dueDate || null;
    out.dueDateTime = replyDraft.dueDateTime || null;
  }

  if (out.needsPriorityClarify) {
    out.step = "await_priority";
  } else {
    out.step = "await_confirm";
  }
  delete out.pendingTime;
  return out;
}

function unresolvedPrompt(pending) {
  const cnt = pending.unresolvedIndexes.length;
  return [
    `Для ${cnt} задач не нашёл срок.`,
    "Указать общий срок? (сегодня/завтра/дд.мм/гггг-мм-дд/по одной/без срока)"
  ].join("\n");
}

function buildVoicePendingFromText(cfg, text) {
  const parsed = parseVoiceTasks(text, cfg.tz, cfg.voiceMaxTasks);
  if (!parsed.tasks.length) return { error: "Не смог выделить задачи из голоса. Отправьте текстом или наговорите еще раз." };
  if (parsed.tasks.length > cfg.voiceMaxTasks || parsed.truncated) {
    return { error: `Слишком много задач. Максимум: ${cfg.voiceMaxTasks}.` };
  }

  const tasks = parsed.tasks.map((t) => {
    const p = detectPriority(t.content, cfg);
    return {
      ...t,
      content: p.content,
      priority: p.priority,
      todoistPriority: p.todoistPriority,
      priorityConfidence: p.confidence,
      needsPriorityClarify: p.needsClarify
    };
  });

  const unresolvedIndexes = [];
  const unresolvedPriorityIndexes = [];

  tasks.forEach((t, idx) => {
    if (!t.dueDate && !t.dueDateTime) unresolvedIndexes.push(idx);
    if (t.needsPriorityClarify) unresolvedPriorityIndexes.push(idx);
  });

  const pending = {
    transcript: parsed.transcript,
    tasks,
    unresolvedIndexes,
    unresolvedPriorityIndexes,
    resolveCursor: 0,
    priorityCursor: 0,
    lowConfidence: parsed.lowConfidence,
    step: "voice_waiting_confirmation"
  };

  if (unresolvedIndexes.length) pending.step = "voice_waiting_date_resolution";
  else if (unresolvedPriorityIndexes.length) pending.step = "voice_waiting_priority_resolution";

  return { pending };
}

function applySinglePriorityOverride(pending, msg) {
  const p = parsePriorityAnswer(msg);
  if (!p) return false;
  applyPriority(pending, p);
  pending.needsPriorityClarify = false;
  return true;
}

function applyVoicePriorityOverrideAll(pending, msg) {
  const p = parsePriorityAnswer(msg);
  if (!p) return false;
  pending.tasks = pending.tasks.map((task) => ({
    ...task,
    priority: p,
    todoistPriority: priorityToTodoist(p),
    needsPriorityClarify: false
  }));
  pending.unresolvedPriorityIndexes = [];
  pending.priorityCursor = 0;
  return true;
}

async function main() {
  const cfg = getConfig();
  const { userId, text } = parseArgs();
  const msg = (text || "").trim();
  const uid = String(userId || "").trim();

  if (!uid) {
    console.log("__NOOP__");
    return;
  }

  if (!isOwnerUser(uid, cfg.telegramOwnerId)) {
    console.log("Эта команда доступна только владельцу.");
    return;
  }

  if (!msg) {
    console.log("__NOOP__");
    return;
  }

  let meetingFlow = null;
  try {
    meetingFlow = await handleMeetingFlow(cfg, uid, msg);
  } catch (err) {
    console.log(`Ошибка календаря: ${err.message || err}`);
    return;
  }
  if (meetingFlow?.handled) {
    console.log(meetingFlow.text || "__NOOP__");
    return;
  }

  inferAssistantReactionFromMessage(cfg, msg);

  const wipePending = getProfileWipePending(cfg.stateDir, uid);
  if (wipePending) {
    if (isYes(msg)) {
      wipeTelemetry(cfg.stateDir);
      clearProfileWipePending(cfg.stateDir, uid);
      console.log("Профиль очищен ✅ Все персональные данные удалены.");
      return;
    }
    if (isNo(msg)) {
      clearProfileWipePending(cfg.stateDir, uid);
      console.log("Ок, очистку отменил.");
      return;
    }
  }

  if (/^\/priority_help\b/i.test(msg)) {
    console.log(priorityHelpText());
    return;
  }

  if (/^\/add_cancel\b/i.test(msg)) {
    clearPending(cfg.stateDir, uid);
    console.log("Ок, отменил добавление задачи.");
    return;
  }




  if (/^\/profile\b/i.test(msg)) {
    const action = (msg.split(/\s+/)[1] || "status").toLowerCase();
    if (action === "on") {
      setProfileEnabled(cfg.stateDir, true);
      console.log("Профиль персонализации включён ✅");
      return;
    }
    if (action === "off") {
      setProfileEnabled(cfg.stateDir, false);
      console.log("Профиль персонализации выключен ⏸️");
      return;
    }
    if (action === "wipe") {
      setProfileWipePending(cfg.stateDir, uid);
      console.log("Подтвердите удаление персональных данных: да/нет");
      return;
    }
    const enabled = isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false);
    console.log([
      "Статус профиля:",
      `• Включён: ${enabled ? "да" : "нет"}`,
      "Команды: /profile on | /profile off | /profile wipe"
    ].join("\n"));
    return;
  }

  if (/^\/me\b/i.test(msg)) {
    console.log(formatMeInsights(cfg));
    return;
  }
  if (/^\/assistant\b/i.test(msg)) {
    const action = (msg.split(/\s+/)[1] || "status").toLowerCase();
    if (action === "on") {
      setExecutionEnabled(cfg.stateDir, true);
      console.log("Execution mode включён ✅");
      return;
    }
    if (action === "off") {
      setExecutionEnabled(cfg.stateDir, false);
      try { recordAssistantEvent(cfg, "assistant_off", "command", {}); } catch {}
      console.log("Execution mode выключен ⏸️");
      return;
    }
    const st = getExecutionStatus(cfg, new Date());
    const last = st.lastAdviceAt
      ? new Intl.DateTimeFormat("ru-RU", { timeZone: cfg.tz, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(st.lastAdviceAt))
      : "ещё не было";

    console.log([
      `Execution mode: ${st.enabled ? "ON" : "OFF"}`,
      `Последняя рекомендация: ${last}`,
      `Следующая проверка: ${st.nextCheckAt}`
    ].join("\n"));
    return;
  }

  if (/^\/reminders\b/i.test(msg)) {
    const action = (msg.split(/\s+/)[1] || "status").toLowerCase();
    if (action === "on") {
      setRemindersEnabled(cfg.stateDir, true);
      try { recordAssistantEvent(cfg, "dnd_off", "reminders", {}); } catch {}
      console.log("Напоминания включены ✅");
      return;
    }
    if (action === "off") {
      setRemindersEnabled(cfg.stateDir, false);
      try { recordAssistantEvent(cfg, "assistant_off", "reminders_off", {}); } catch {}
      console.log("Напоминания выключены ⏸️");
      return;
    }
    const st = getRemindersStatus(cfg.stateDir, cfg);
    console.log([
      "Статус напоминаний:",
      `• Включены: ${st.enabled ? "да" : "нет"}`,
      `• До задачи: ${st.preMin} мин`,
      `• Follow-up: ${st.followupMin} мин`,
      `• Стиль: ${st.style}`,
      `• Последний тик: ${st.lastRunAt || "ещё не было"}`
    ].join("\n"));
    return;
  }


  if (/^\/(day|agenda|free|diag|sync_status|connect_google|connect_bitrix|oauth_google|oauth_bitrix)\b/i.test(msg)) {
    const parts = msg.trim().split(/\s+/);
    const cmdName = parts[0].replace(/^\//, "").toLowerCase();
    const cmdArg = msg.replace(/^\/\w+\s*/i, "");
    const out = await runAgendaCommand(cmdName, cmdArg);
    console.log(out || "__NOOP__");
    return;
  }

  const todayIso = dateISOInTz(new Date(), cfg.tz);

  if (/^\/focus_blocks\b/i.test(msg)) {
    const blocks = (loadFocusBlocks(cfg.stateDir).entries || []).filter((x) => x.date === todayIso && x.status !== "canceled");
    if (blocks.length) {
      console.log(formatFocusBlocksMessage(blocks));
      return;
    }
    const proposal = getFocusProposal(cfg.stateDir);
    if (proposal?.date === todayIso && proposal?.blocks?.length) {
      console.log(formatFocusBlocksMessage(proposal.blocks));
      return;
    }
    console.log("На сегодня фокус-блоки не запланированы.");
    return;
  }

  if (/^\/focus_accept\b/i.test(msg)) {
    const accepted = acceptFocusProposal(cfg.stateDir, todayIso);
    if (!accepted.ok) {
      console.log(accepted.error);
      return;
    }
    console.log(formatFocusBlocksMessage(accepted.blocks, "🧱 Фокус-блоки сохранены"));
    return;
  }

  if (/^\/focus_edit\b/i.test(msg)) {
    const arg = msg.replace(/^\/focus_edit\b/i, "").trim();
    const proposal = getFocusProposal(cfg.stateDir);
    if (!arg) {
      console.log("Укажите диапазоны: /focus_edit 10:30-11:30,15:00-16:00");
      return;
    }
    const edited = editFocusBlocks(cfg.stateDir, todayIso, arg, proposal?.date === todayIso ? proposal : null);
    if (!edited.ok) {
      console.log(edited.error);
      return;
    }
    console.log(formatFocusBlocksMessage(edited.blocks, "🧱 Фокус-блоки обновлены"));
    return;
  }

  if (/^\/focus_off\b/i.test(msg)) {
    cancelFocusBlocks(cfg.stateDir, todayIso);
    console.log("Фокус-блоки на сегодня отключены.");
    return;
  }

  if (/^\/dnd\b/i.test(msg)) {
    const parts = msg.split(/\s+/).filter(Boolean);
    const action = (parts[1] || "status").toLowerCase();
    if (action === "on") {
      setDnd(cfg.stateDir, true);
      try { recordAssistantEvent(cfg, "dnd_on", "command", {}); } catch {}
      console.log("DND включён ✅");
      return;
    }
    if (action === "off") {
      setDnd(cfg.stateDir, false);
      try { recordAssistantEvent(cfg, "dnd_off", "command", {}); } catch {}
      console.log("DND выключен ✅");
      return;
    }
    if (action === "set") {
      const start = parts[2] || "";
      const end = parts[3] || "";
      const changed = setDndWindow(cfg.stateDir, start, end);
      if (!changed.ok) {
        console.log(changed.error);
        return;
      }
      console.log(`DND окно обновлено: ${changed.settings.nightStart}–${changed.settings.nightEnd}`);
      return;
    }
    const st = getDndStatus(cfg, new Date());
    console.log([
      "Статус DND:",
      `• Включен: ${st.enabled ? "да" : "нет"}`,
      `• Ночь: ${st.nightStart}–${st.nightEnd}`,
      `• Активен сейчас: ${st.activeNow ? "да" : "нет"}`,
      `• Причина: ${st.reason}`
    ].join("\n"));
    return;
  }

  const rsp = getRescheduleConfirm(cfg.stateDir, uid);
  if (rsp && isYes(msg)) {
    const provider = createProvider(cfg);
    let mode = "local";
    if (rsp.planned_due_datetime !== "keep") {
      try {
        if (typeof provider.updateTaskDue === "function") {
          await provider.updateTaskDue(rsp.task_id, { dueDateTime: rsp.planned_due_datetime });
          mode = "api";
        }
      } catch {
        mode = "local";
      }
    }
    saveRescheduleRecord(cfg.stateDir, {
      task_id: rsp.task_id,
      planned_due_datetime: rsp.planned_due_datetime,
      source: rsp.source || "user",
      apply_mode: mode
    });
    clearRescheduleConfirm(cfg.stateDir, uid);
    if (rsp.planned_due_datetime === "keep") {
      console.log("Ок, оставил задачу без переноса.");
    } else {
      console.log(`Готово ✅ План переноса сохранён: ${rsp.planned_due_datetime}${mode === "api" ? " (обновлено в to-do)" : " (локальный план)"}`);
    }
    return;
  }
  if (rsp && isNo(msg)) {
    clearRescheduleConfirm(cfg.stateDir, uid);
    console.log("Ок, перенос отменён.");
    return;
  }

  if (/^\/reschedule\b/i.test(msg)) {
    const parts = msg.split(/\s+/).filter(Boolean);
    const taskId = parts[1] || "";
    const target = parts[2] || "";
    if (!taskId || !target) {
      console.log("Формат: /reschedule <task_id> <YYYY-MM-DDTHH:MM:SS+03:00|keep>");
      return;
    }

    const planned = target.toLowerCase() === "keep" ? "keep" : target;
    queueRescheduleConfirm(cfg.stateDir, uid, {
      task_id: taskId,
      planned_due_datetime: planned,
      source: "user"
    });

    console.log([
      "Подтвердите перенос:",
      `• task_id: ${taskId}`,
      `• новый срок: ${planned === "keep" ? "оставить как есть" : planned}`,
      "Ок? (да/нет)"
    ].join("\n"));
    return;
  }
  const pending = getPending(cfg.stateDir, uid);
  if (pending) {
    if (pending.step === "await_date") {
      if (applySinglePriorityOverride(pending, msg)) {
        setPending(cfg.stateDir, uid, pending);
        console.log(`Обновил приоритет: ${priorityLabel(pending.priority || "P3")}`);
        return;
      }

      if (isNoDate(msg)) {
        const next = { ...pending, dueDate: null, dueDateTime: null };
        delete next.pendingTime;
        next.step = next.needsPriorityClarify ? "await_priority" : "await_confirm";
        setPending(cfg.stateDir, uid, next);
        if (next.step === "await_priority") console.log(priorityQuestion());
        else console.log(previewText(next));
        return;
      }

      const replyDraft = parseAddDraft(msg, cfg.tz);
      const next = finalizeWithDateReply(pending, replyDraft);
      if (!next) {
        console.log("Не понял дату. Укажите: сегодня/завтра/ДД.ММ/YYYY-MM-DD/без даты");
        return;
      }

      setPending(cfg.stateDir, uid, next);
      if (next.step === "await_priority") console.log(priorityQuestion());
      else console.log(previewText(next));
      return;
    }

    if (pending.step === "await_priority") {
      const p = parsePriorityAnswer(msg);
      if (!p) {
        console.log(priorityQuestion());
        return;
      }
      const next = { ...pending, priority: p, todoistPriority: priorityToTodoist(p), needsPriorityClarify: false, step: "await_confirm" };
      setPending(cfg.stateDir, uid, next);
      console.log(previewText(next));
      return;
    }

    if (pending.step === "await_confirm") {
      if (applySinglePriorityOverride(pending, msg) || /сделай\s+приоритет/i.test(msg)) {
        setPending(cfg.stateDir, uid, pending);
        console.log(previewText(pending));
        return;
      }

      if (isYes(msg)) {
        const result = await createTaskOrDryRun(cfg, pending, pending.source || "text");
        clearPending(cfg.stateDir, uid);
        if (result.dryRun) {
          console.log(result.message);
          return;
        }
        const link = result.created?.url ? `\nСсылка: ${result.created.url}` : "";
        console.log(`Готово ✅ Добавил.${link}`);
        return;
      }
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        console.log("Ок, не добавляю.");
        return;
      }
      console.log("Подтвердите, пожалуйста: да/нет");
      return;
    }

    if (pending.step === "voice_waiting_date_resolution") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        console.log("Ок, отменил добавление из голоса. Отправить текстом исправленный список?");
        return;
      }

      if (isResolveEach(msg)) {
        const next = { ...pending, step: "voice_waiting_date_resolution_each", resolveCursor: 0 };
        setPending(cfg.stateDir, uid, next);
        const idx = next.unresolvedIndexes[0];
        console.log(`Задача: ${next.tasks[idx].content}\nНа какую дату поставить? (сегодня/завтра/дд.мм/гггг-мм-дд/без срока)`);
        return;
      }

      const choice = parseDateChoice(msg, cfg.tz);
      if (!choice.ok) {
        console.log("Не понял. Укажите общий срок: сегодня/завтра/дд.мм/гггг-мм-дд/по одной/без срока");
        return;
      }

      const next = { ...pending };
      next.unresolvedIndexes.forEach((idx) => applyDateResolution(next.tasks[idx], choice));
      next.unresolvedIndexes = [];
      if (next.unresolvedPriorityIndexes.length) next.step = "voice_waiting_priority_resolution";
      else next.step = "voice_waiting_confirmation";
      setPending(cfg.stateDir, uid, next);
      if (next.step === "voice_waiting_priority_resolution") {
        const idx = next.unresolvedPriorityIndexes[next.priorityCursor || 0];
        console.log(`Задача: ${next.tasks[idx].content}\n${priorityQuestion()}`);
      } else {
        console.log(voicePreviewText(next));
      }
      return;
    }

    if (pending.step === "voice_waiting_date_resolution_each") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        console.log("Ок, отменил добавление из голоса. Отправить текстом исправленный список?");
        return;
      }

      const current = pending.unresolvedIndexes[pending.resolveCursor];
      const choice = parseDateChoice(msg, cfg.tz);
      if (!choice.ok) {
        console.log("Не понял дату. Ответьте: сегодня/завтра/дд.мм/гггг-мм-дд/без срока");
        return;
      }

      const next = { ...pending };
      applyDateResolution(next.tasks[current], choice);
      next.resolveCursor += 1;

      if (next.resolveCursor >= next.unresolvedIndexes.length) {
        next.unresolvedIndexes = [];
        if (next.unresolvedPriorityIndexes.length) {
          next.step = "voice_waiting_priority_resolution";
          setPending(cfg.stateDir, uid, next);
          const idx = next.unresolvedPriorityIndexes[next.priorityCursor || 0];
          console.log(`Задача: ${next.tasks[idx].content}\n${priorityQuestion()}`);
        } else {
          next.step = "voice_waiting_confirmation";
          setPending(cfg.stateDir, uid, next);
          console.log(voicePreviewText(next));
        }
        return;
      }

      setPending(cfg.stateDir, uid, next);
      const idx = next.unresolvedIndexes[next.resolveCursor];
      console.log(`Задача: ${next.tasks[idx].content}\nНа какую дату поставить? (сегодня/завтра/дд.мм/гггг-мм-дд/без срока)`);
      return;
    }

    if (pending.step === "voice_waiting_priority_resolution") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        console.log("Ок, отменил добавление из голоса. Отправить текстом исправленный список?");
        return;
      }

      if (applyVoicePriorityOverrideAll(pending, msg)) {
        pending.step = "voice_waiting_confirmation";
        setPending(cfg.stateDir, uid, pending);
        console.log(voicePreviewText(pending));
        return;
      }

      const p = parsePriorityAnswer(msg);
      if (!p) {
        console.log(priorityQuestion());
        return;
      }

      const next = { ...pending };
      const idx = next.unresolvedPriorityIndexes[next.priorityCursor];
      applyPriority(next.tasks[idx], p);
      next.tasks[idx].needsPriorityClarify = false;
      next.priorityCursor += 1;

      if (next.priorityCursor >= next.unresolvedPriorityIndexes.length) {
        next.unresolvedPriorityIndexes = [];
        next.step = "voice_waiting_confirmation";
        setPending(cfg.stateDir, uid, next);
        console.log(voicePreviewText(next));
        return;
      }

      setPending(cfg.stateDir, uid, next);
      const nextIdx = next.unresolvedPriorityIndexes[next.priorityCursor];
      console.log(`Задача: ${next.tasks[nextIdx].content}\n${priorityQuestion()}`);
      return;
    }

    if (pending.step === "voice_waiting_confirmation") {
      if (applyVoicePriorityOverrideAll(pending, msg) || /сделай\s+приоритет/i.test(msg)) {
        setPending(cfg.stateDir, uid, pending);
        console.log(voicePreviewText(pending));
        return;
      }

      if (isYes(msg)) {
        const result = await createBatch(cfg, pending.tasks);
        clearPending(cfg.stateDir, uid);
        console.log(result);
        return;
      }
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        console.log("Ок, не добавляю. Отправить текстом исправленный список?");
        return;
      }
      console.log("Подтвердите, пожалуйста: да/нет");
      return;
    }
  }

  const forcedAdd = /^\/add\b/i.test(msg);
  const intent = detectAddIntent(msg);
  const shouldTryVoiceBatch = looksLikeVoiceBatch(msg);

  if (!forcedAdd && !intent.isAdd && !shouldTryVoiceBatch) {
    console.log("__NOOP__");
    return;
  }

  if (shouldTryVoiceBatch && !/^\/tasks\b/i.test(msg) && !/^\/overdue\b/i.test(msg)) {
    const built = buildVoicePendingFromText(cfg, msg);
    if (built.error) {
      console.log(built.error);
      return;
    }

    setPending(cfg.stateDir, uid, built.pending);
    if (built.pending.step === "voice_waiting_date_resolution") {
      console.log([`Я услышал:\n${built.pending.transcript}\n`, unresolvedPrompt(built.pending)].join("\n"));
      return;
    }
    if (built.pending.step === "voice_waiting_priority_resolution") {
      const idx = built.pending.unresolvedPriorityIndexes[0];
      console.log(`Я услышал:\n${built.pending.transcript}\n\nЗадача: ${built.pending.tasks[idx].content}\n${priorityQuestion()}`);
      return;
    }

    console.log(voicePreviewText(built.pending));
    return;
  }

  const draft = parseAddDraft(msg, cfg.tz);
  if (!draft.content) {
    console.log("Напишите текст задачи после /add. Например: /add отправить КП завтра 10:30");
    return;
  }

  const pri = detectPriority(draft.content, cfg);

  const p = {
    content: pri.content,
    priority: pri.priority,
    todoistPriority: pri.todoistPriority,
    priorityConfidence: pri.confidence,
    needsPriorityClarify: pri.needsClarify,
    dueDate: draft.dueDate,
    dueDateTime: draft.dueDateTime,
    pendingTime: draft.parsed.timeToken || null,
    step: "await_confirm"
  };

  if (draft.needDateClarify) {
    p.step = "await_date";
    p.dueDate = null;
    p.dueDateTime = null;
    setPending(cfg.stateDir, uid, p);
    if (draft.hasTime) {
      console.log("Указано время без даты. На какую дату поставить задачу? (сегодня/завтра/дд.мм/гггг-мм-дд/без даты)");
    } else {
      console.log("На какую дату поставить задачу? (сегодня/завтра/дд.мм/гггг-мм-дд/без даты)");
    }
    return;
  }

  if (p.needsPriorityClarify) {
    p.step = "await_priority";
    setPending(cfg.stateDir, uid, p);
    console.log(priorityQuestion());
    return;
  }

  setPending(cfg.stateDir, uid, p);
  console.log(previewText(p));
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
