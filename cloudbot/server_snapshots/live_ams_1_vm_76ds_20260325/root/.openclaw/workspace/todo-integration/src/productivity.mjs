import { dateISOInTz } from "./time.mjs";
import {
  loadDndSettings,
  loadFocusBlocks,
  loadFocusProposal,
  loadReschedulePending,
  loadSuppressedNotifications,
  loadTaskReschedules,
  saveDndSettings,
  saveFocusBlocks,
  saveFocusProposal,
  saveReschedulePending,
  saveSuppressedNotifications,
  saveTaskReschedules
} from "./productivity-state.mjs";

function mapPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function hhmmNow(date, tz) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function parseHHMM(v) {
  const m = String(v || "").match(/^(\d{2}):(\d{2})$/);
  if (!m) return null;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (hh > 23 || mm > 59) return null;
  return { hh, mm, raw: `${m[1]}:${m[2]}` };
}

function isInsideWindow(nowHHMM, startHHMM, endHHMM) {
  const toM = (x) => Number(x.slice(0, 2)) * 60 + Number(x.slice(3, 5));
  const n = toM(nowHHMM);
  const s = toM(startHHMM);
  const e = toM(endHHMM);
  if (s <= e) return n >= s && n < e;
  return n >= s || n < e;
}

function parseDueTimeHHMM(task, tz) {
  if (!task.dueDateTime) return null;
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(task.dueDateTime));
  } catch {
    return null;
  }
}

function overlaps(taskHHMM, startHHMM, endHHMM) {
  if (!taskHHMM) return false;
  return isInsideWindow(taskHHMM, startHHMM, endHHMM);
}

function suggestDurationMins(tasksCount) {
  return tasksCount >= 5 ? 90 : 60;
}

export function buildFocusProposal(tasks, cfg, dateIso) {
  const timed = tasks.filter((t) => !!t.dueDateTime);
  const candidates = tasks
    .filter((t) => !t.dueDateTime)
    .map((t) => ({ ...t, displayPriority: mapPriority(t) }))
    .filter((t) => t.displayPriority <= 2)
    .sort((a, b) => a.displayPriority - b.displayPriority)
    .slice(0, 3);

  if (!candidates.length) return null;

  const duration = suggestDurationMins(tasks.length);
  const windows = String(cfg.focusPreferredWindows || "10:00-11:00,12:00-13:00,15:00-16:00")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((raw) => {
      const [a, b] = raw.split("-").map((x) => x.trim());
      return { start: a, end: b };
    })
    .filter((w) => parseHHMM(w.start) && parseHHMM(w.end));

  const free = windows.filter((w) => {
    const conflict = timed.some((t) => overlaps(parseDueTimeHHMM(t, cfg.tz), w.start, w.end));
    return !conflict;
  });

  const blockCount = candidates.length >= 3 ? 2 : 1;
  const selected = free.slice(0, blockCount);
  if (!selected.length) return null;

  const taskBuckets = [candidates.slice(0, 2), candidates.slice(2, 3)].filter((x) => x.length);

  const blocks = selected.map((w, i) => {
    const tasksForBlock = taskBuckets[i] || candidates.slice(0, 1);
    const title = tasksForBlock.map((t) => t.content).join(" + ");
    let end = w.end;
    if (duration === 90) {
      const p = parseHHMM(w.start);
      if (p) {
        const m = p.hh * 60 + p.mm + 90;
        const hh = String(Math.floor((m % (24 * 60)) / 60)).padStart(2, "0");
        const mm = String(m % 60).padStart(2, "0");
        end = `${hh}:${mm}`;
      }
    }
    return {
      date: dateIso,
      start_time: w.start,
      end_time: end,
      title,
      related_task_ids: tasksForBlock.map((t) => String(t.id)).filter(Boolean),
      status: "planned",
      pre_sent_at: null,
      start_sent_at: null,
      end_sent_at: null,
      created_at: new Date().toISOString()
    };
  });

  return { date: dateIso, blocks, created_at: new Date().toISOString() };
}

export function saveFocusProposalForDate(stateDir, proposal) {
  saveFocusProposal(stateDir, { proposal });
}

export function getFocusProposal(stateDir) {
  return loadFocusProposal(stateDir).proposal || null;
}

export function acceptFocusProposal(stateDir, dateIso) {
  const p = loadFocusProposal(stateDir).proposal;
  if (!p || p.date !== dateIso) return { ok: false, error: "Нет актуального предложения фокус-блоков." };
  const st = loadFocusBlocks(stateDir);
  st.entries = (st.entries || []).filter((x) => x.date !== dateIso || x.status === "done" || x.status === "canceled");
  st.entries.push(...p.blocks);
  saveFocusBlocks(stateDir, st);
  saveFocusProposal(stateDir, { proposal: null });
  return { ok: true, blocks: p.blocks };
}

export function cancelFocusBlocks(stateDir, dateIso) {
  const st = loadFocusBlocks(stateDir);
  st.entries = (st.entries || []).map((x) => {
    if (x.date === dateIso && x.status !== "done") return { ...x, status: "canceled" };
    return x;
  });
  saveFocusBlocks(stateDir, st);
  saveFocusProposal(stateDir, { proposal: null });
  return { ok: true };
}

export function editFocusBlocks(stateDir, dateIso, rangesCsv, proposalFallback = null) {
  const ranges = String(rangesCsv || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((raw) => {
      const [start, end] = raw.split("-").map((x) => x.trim());
      if (!parseHHMM(start) || !parseHHMM(end)) return null;
      return { start, end };
    })
    .filter(Boolean);

  if (!ranges.length) return { ok: false, error: "Формат: /focus_edit 10:30-11:30,15:00-16:00" };

  const source = proposalFallback?.blocks?.length ? proposalFallback.blocks : loadFocusBlocks(stateDir).entries.filter((x) => x.date === dateIso);
  const tasks = source.flatMap((x) => x.related_task_ids || []);

  const entries = ranges.map((r, i) => ({
    date: dateIso,
    start_time: r.start,
    end_time: r.end,
    title: source[i]?.title || `Фокус-блок ${i + 1}`,
    related_task_ids: source[i]?.related_task_ids || tasks.slice(i, i + 1),
    status: "planned",
    pre_sent_at: null,
    start_sent_at: null,
    end_sent_at: null,
    created_at: new Date().toISOString()
  }));

  const st = loadFocusBlocks(stateDir);
  st.entries = (st.entries || []).filter((x) => x.date !== dateIso || x.status === "done" || x.status === "canceled");
  st.entries.push(...entries);
  saveFocusBlocks(stateDir, st);
  saveFocusProposal(stateDir, { proposal: null });
  return { ok: true, blocks: entries };
}

export function formatFocusBlocksMessage(blocks, title = "🧱 Фокус-блоки на сегодня") {
  if (!blocks?.length) return `${title}\nНет активных фокус-блоков.`;
  const lines = [title];
  blocks.forEach((b, i) => {
    lines.push(`${i + 1}) ${b.start_time}–${b.end_time} — ${b.title}`);
  });
  lines.push("", "Команды: /focus_accept /focus_edit 10:30-11:30,15:00-16:00 /focus_off");
  return lines.join("\n");
}

function nowDateAndTime(cfg, now = new Date()) {
  return {
    dateIso: dateISOInTz(now, cfg.tz),
    hhmm: hhmmNow(now, cfg.tz)
  };
}

export function isDndActive(cfg, now = new Date()) {
  const settings = loadDndSettings(cfg.stateDir, {
    enabled: cfg.dndEnabled,
    nightStart: cfg.dndNightStart,
    nightEnd: cfg.dndNightEnd
  });

  if (!settings.enabled) {
    return { active: false, reason: null, settings };
  }

  const nt = nowDateAndTime(cfg, now);
  if (isInsideWindow(nt.hhmm, settings.nightStart, settings.nightEnd)) {
    return { active: true, reason: "night", settings };
  }

  const blocks = loadFocusBlocks(cfg.stateDir).entries || [];
  const inFocus = blocks.find((b) => b.date === nt.dateIso && b.status !== "canceled" && isInsideWindow(nt.hhmm, b.start_time, b.end_time));
  if (inFocus) return { active: true, reason: "focus", block: inFocus, settings };

  return { active: false, reason: null, settings };
}

export function shouldAllowDuringDnd(meta) {
  const priority = Number(meta.displayPriority || 3);
  if (priority === 1) return true;
  if (meta.isOverdue && priority === 1) return true;
  if (meta.hasFixedTime && priority <= 2) return true;
  return false;
}

export function queueSuppressedNotification(stateDir, item) {
  const st = loadSuppressedNotifications(stateDir);
  st.entries.push({ ...item, created_at: new Date().toISOString() });
  if (st.entries.length > 5000) st.entries = st.entries.slice(-5000);
  saveSuppressedNotifications(stateDir, st);
}

export function flushSuppressedSummary(stateDir) {
  const st = loadSuppressedNotifications(stateDir);
  const total = st.entries.length;
  if (!total) return null;
  const top = st.entries.slice(-3);
  const lines = [`Пока был DND, пропущено: ${total} уведомлений`];
  top.forEach((x) => lines.push(`• ${x.title || x.type || "уведомление"}`));
  st.entries = [];
  st.lastFlushAt = new Date().toISOString();
  saveSuppressedNotifications(stateDir, st);
  return lines.join("\n");
}

export function setDnd(stateDir, enabled) {
  const current = loadDndSettings(stateDir, {});
  const next = { ...current, enabled: !!enabled };
  saveDndSettings(stateDir, next);
  return next;
}

export function setDndWindow(stateDir, startHHMM, endHHMM) {
  if (!parseHHMM(startHHMM) || !parseHHMM(endHHMM)) {
    return { ok: false, error: "Формат: /dnd set 22:30 08:30" };
  }
  const current = loadDndSettings(stateDir, {});
  const next = { ...current, nightStart: startHHMM, nightEnd: endHHMM };
  saveDndSettings(stateDir, next);
  return { ok: true, settings: next };
}

export function getDndStatus(cfg, now = new Date()) {
  const status = isDndActive(cfg, now);
  return {
    enabled: status.settings.enabled,
    nightStart: status.settings.nightStart,
    nightEnd: status.settings.nightEnd,
    activeNow: status.active,
    reason: status.reason || "none"
  };
}

export function createRescheduleSuggestion(task, now = new Date()) {
  const p = mapPriority(task);
  const today = new Date(now);
  const hh = today.getHours();
  const mm = today.getMinutes();
  const plus30 = new Date(today.getTime() + 30 * 60 * 1000);
  const yyyy = plus30.getFullYear();
  const mo = String(plus30.getMonth() + 1).padStart(2, "0");
  const dd = String(plus30.getDate()).padStart(2, "0");
  const h2 = String(plus30.getHours()).padStart(2, "0");
  const m2 = String(plus30.getMinutes()).padStart(2, "0");
  const plus30IsoLocal = `${yyyy}-${mo}-${dd}T${h2}:${m2}:00+03:00`;

  const tomorrow = new Date(today.getTime() + 24 * 3600 * 1000);
  const ty = tomorrow.getFullYear();
  const tm = String(tomorrow.getMonth() + 1).padStart(2, "0");
  const td = String(tomorrow.getDate()).padStart(2, "0");
  const tomorrow1000 = `${ty}-${tm}-${td}T10:00:00+03:00`;

  return {
    taskId: String(task.id),
    title: String(task.content || "Задача"),
    priority: p,
    options: {
      tomorrow10: tomorrow1000,
      plus30: hh < 23 || (hh === 23 && mm <= 20) ? plus30IsoLocal : null,
      keep: "keep"
    }
  };
}

export function queueRescheduleConfirm(stateDir, userId, action) {
  const st = loadReschedulePending(stateDir);
  st.byUser[String(userId)] = { ...action, created_at: new Date().toISOString() };
  saveReschedulePending(stateDir, st);
}

export function getRescheduleConfirm(stateDir, userId) {
  const st = loadReschedulePending(stateDir);
  return st.byUser[String(userId)] || null;
}

export function clearRescheduleConfirm(stateDir, userId) {
  const st = loadReschedulePending(stateDir);
  delete st.byUser[String(userId)];
  saveReschedulePending(stateDir, st);
}

export function saveRescheduleRecord(stateDir, rec) {
  const st = loadTaskReschedules(stateDir);
  st.entries.push({ ...rec, created_at: new Date().toISOString() });
  if (st.entries.length > 5000) st.entries = st.entries.slice(-5000);
  saveTaskReschedules(stateDir, st);
}

export function formatRescheduleSuggestions(items) {
  if (!items.length) return "Критичных задач для переноса нет.";
  const lines = ["♻️ Предложения по переносу"]; 
  items.slice(0, 5).forEach((x) => {
    lines.push(`• ${x.title}`);
    lines.push(`  /reschedule ${x.taskId} ${x.options.tomorrow10}`);
    if (x.options.plus30) lines.push(`  /reschedule ${x.taskId} ${x.options.plus30}`);
    lines.push(`  /reschedule ${x.taskId} keep`);
  });
  return lines.join("\n");
}

export function pickCriticalForReschedule(tasks) {
  return tasks
    .map((t) => ({ ...t, displayPriority: mapPriority(t) }))
    .filter((t) => t.displayPriority <= 2);
}
