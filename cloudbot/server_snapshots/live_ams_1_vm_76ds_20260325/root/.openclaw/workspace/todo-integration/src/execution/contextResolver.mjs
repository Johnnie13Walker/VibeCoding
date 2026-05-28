function hhmmToMinutes(v) {
  const m = String(v || "").match(/^(\d{2}):(\d{2})$/);
  if (!m) return null;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (hh > 23 || mm > 59) return null;
  return hh * 60 + mm;
}

function toHHMM(date, tz) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function durationMin(startHHMM, endHHMM) {
  const s = hhmmToMinutes(startHHMM);
  const e = hhmmToMinutes(endHHMM);
  if (s == null || e == null) return 0;
  return Math.max(0, e - s);
}

function mapPriority(task) {
  const p = Number(task.priority || task.todoistPriority || 2);
  if (p >= 4) return 1;
  if (p === 3) return 2;
  if (p === 2) return 3;
  return 4;
}

function normalizeTaskTitle(content = "") {
  return String(content)
    .replace(/\[[^\]]+\]\((https?:\/\/[^\s)]+)\)/gi, " ")
    .replace(/https?:\/\/\S+/gi, " ")
    .replace(/\s+/g, " ")
    .trim() || "Задача";
}

function estimateTaskMinutes(task) {
  const txt = String(task.content || "").toLowerCase();
  if (/(созвон|встреч|звонок|call)/i.test(txt)) return 30;
  if (/(провер|ответ|почт|оплат|сверк|дубли|перезвон)/i.test(txt)) return 25;
  if (/(подготов|разработ|договор|отчет|отчёт|kpi|презентац|стратег)/i.test(txt)) return 70;
  return 45;
}

function sortTasks(tasks, tz, nowMs) {
  return [...(tasks || [])]
    .map((t) => {
      let dueTs = null;
      if (t.dueDateTime) {
        const ts = new Date(t.dueDateTime).getTime();
        if (Number.isFinite(ts)) dueTs = ts;
      }
      const dueTodayTimed = dueTs != null;
      const minToDue = dueTs != null ? Math.floor((dueTs - nowMs) / 60000) : null;
      return {
        ...t,
        displayPriority: mapPriority(t),
        title: normalizeTaskTitle(t.content),
        etaMin: estimateTaskMinutes(t),
        dueTs,
        dueTodayTimed,
        minToDue
      };
    })
    .sort((a, b) => {
      if (a.displayPriority !== b.displayPriority) return a.displayPriority - b.displayPriority;
      const aTimed = a.dueTodayTimed ? 0 : 1;
      const bTimed = b.dueTodayTimed ? 0 : 1;
      if (aTimed !== bTimed) return aTimed - bTimed;
      if ((a.dueTs || 0) !== (b.dueTs || 0)) return (a.dueTs || 0) - (b.dueTs || 0);
      return a.title.localeCompare(b.title, "ru");
    });
}

function resolveMeetingContext(meetings, nowMs) {
  const sorted = [...(meetings || [])]
    .filter((m) => !m?.isAllDay)
    .map((m) => {
      const startMs = new Date(m.start).getTime();
      const endMs = new Date(m.end).getTime();
      return Number.isFinite(startMs) && Number.isFinite(endMs) ? { ...m, startMs, endMs } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.startMs - b.startMs);

  let currentMeeting = null;
  let nextMeeting = null;
  let lastEndedMeeting = null;

  for (const m of sorted) {
    if (nowMs >= m.startMs && nowMs < m.endMs) {
      currentMeeting = m;
      break;
    }
    if (m.startMs > nowMs) {
      nextMeeting = m;
      break;
    }
    if (m.endMs <= nowMs) {
      if (!lastEndedMeeting || m.endMs > lastEndedMeeting.endMs) lastEndedMeeting = m;
    }
  }

  const nextIdx = nextMeeting ? sorted.findIndex((x) => x.startMs === nextMeeting.startMs && x.id === nextMeeting.id) : -1;
  const afterNext = nextIdx >= 0 ? sorted[nextIdx + 1] || null : null;

  return {
    meetings: sorted,
    currentMeeting,
    nextMeeting,
    lastEndedMeeting,
    afterNextMeeting: afterNext
  };
}

function workdayLeftMinutes(now, cfg) {
  const nowHHMM = toHHMM(now, cfg.tz);
  const nowMin = hhmmToMinutes(nowHHMM);
  const endMin = hhmmToMinutes(cfg.workdayEnd || "19:00");
  if (nowMin == null || endMin == null) return 0;
  return Math.max(0, endMin - nowMin);
}

export function resolveExecutionContext(now, agenda, cfg) {
  const nowMs = new Date(now).getTime();
  const nowDate = new Date(nowMs);
  const nowHHMM = toHHMM(nowDate, cfg.tz);

  const meetingCtx = resolveMeetingContext(agenda?.meetings || [], nowMs);
  const tasks = sortTasks(agenda?.tasks || [], cfg.tz, nowMs);

  const minutesToNextMeeting = meetingCtx.nextMeeting
    ? Math.floor((meetingCtx.nextMeeting.startMs - nowMs) / 60000)
    : null;

  const minutesSinceLastMeetingEnded = meetingCtx.lastEndedMeeting
    ? Math.floor((nowMs - meetingCtx.lastEndedMeeting.endMs) / 60000)
    : null;

  const freeUntilNextMeeting = meetingCtx.currentMeeting
    ? 0
    : minutesToNextMeeting == null
      ? workdayLeftMinutes(nowDate, cfg)
      : Math.max(0, minutesToNextMeeting);

  const nextMeetingDurationMin = meetingCtx.nextMeeting
    ? Math.max(0, Math.round((meetingCtx.nextMeeting.endMs - meetingCtx.nextMeeting.startMs) / 60000))
    : null;

  const afterMeetingGapMin = meetingCtx.nextMeeting
    ? (meetingCtx.afterNextMeeting
        ? Math.max(0, Math.floor((meetingCtx.afterNextMeeting.startMs - meetingCtx.nextMeeting.endMs) / 60000))
        : workdayLeftMinutes(new Date(meetingCtx.nextMeeting.endMs), cfg))
    : null;

  const totalMeetingMinutes = meetingCtx.meetings.reduce((acc, m) => acc + Math.max(0, Math.round((m.endMs - m.startMs) / 60000)), 0);
  const totalFreeMinutes = (agenda?.freeSlots || []).reduce((acc, s) => acc + durationMin(s.start, s.end), 0);
  const overloaded = totalMeetingMinutes >= 5 * 60 || (tasks.length >= 6 && totalFreeMinutes <= 2 * 60);

  return {
    nowMs,
    nowHHMM,
    date: agenda?.date,
    tasks,
    inMeeting: !!meetingCtx.currentMeeting,
    currentMeeting: meetingCtx.currentMeeting,
    nextMeeting: meetingCtx.nextMeeting,
    lastEndedMeeting: meetingCtx.lastEndedMeeting,
    minutesToNextMeeting,
    minutesSinceLastMeetingEnded,
    freeUntilNextMeeting,
    nextMeetingDurationMin,
    afterMeetingGapMin,
    totalMeetingMinutes,
    totalFreeMinutes,
    overloaded,
    workdayLeftMin: workdayLeftMinutes(nowDate, cfg)
  };
}
