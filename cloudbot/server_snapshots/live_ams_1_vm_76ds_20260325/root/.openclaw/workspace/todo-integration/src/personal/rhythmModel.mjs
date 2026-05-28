import { dateISOInTz } from "../time.mjs";
import { queryAll } from "./storage.mjs";

function toHH(h) {
  return `${String(h).padStart(2, "0")}:00`;
}

function makeWindow(startHour, lenHours = 2) {
  const end = Math.min(24, startHour + lenHours);
  return `${toHH(startHour)}–${toHH(end)}`;
}

function scoreWindow(hoursMap, startHour) {
  let score = 0;
  for (let h = startHour; h < startHour + 2; h += 1) {
    const row = hoursMap.get(h) || { completed: 0, p12: 0, sent: 0, accepted: 0, ignored: 0 };
    score += row.completed * 1.2 + row.p12 * 1.6 + (row.accepted - row.ignored) * 0.8;
  }
  return score;
}

function parsePayloadJson(v) {
  if (!v) return null;
  try { return JSON.parse(v); } catch { return null; }
}

export function buildRhythmModel(cfg, opts = {}) {
  const days = Number(opts.days || 30);
  const minDays = Number(opts.minDays || 7);
  const today = dateISOInTz(new Date(), cfg.tz);

  const completedByHour = queryAll(cfg.stateDir, `
    SELECT CAST(substr(ts, 12, 2) AS INTEGER) AS hour,
           COUNT(*) AS completed,
           SUM(CASE WHEN priority IN (1,2) THEN 1 ELSE 0 END) AS p12
    FROM task_events
    WHERE event_type = 'completed'
      AND ts >= datetime('now', ?)
    GROUP BY hour
  `, [`-${days} days`]);

  const reactionsByHour = queryAll(cfg.stateDir, `
    SELECT CAST(substr(ts, 12, 2) AS INTEGER) AS hour,
           SUM(CASE WHEN event_type='suggestion_sent' THEN 1 ELSE 0 END) AS sent,
           SUM(CASE WHEN event_type='suggestion_accepted' THEN 1 ELSE 0 END) AS accepted,
           SUM(CASE WHEN event_type='suggestion_ignored' THEN 1 ELSE 0 END) AS ignored,
           SUM(CASE WHEN event_type='assistant_off' THEN 1 ELSE 0 END) AS off_count
    FROM assistant_events
    WHERE ts >= datetime('now', ?)
    GROUP BY hour
  `, [`-${days} days`]);

  const activeDaysRow = queryAll(cfg.stateDir, `
    SELECT COUNT(DISTINCT substr(ts, 1, 10)) AS d
    FROM task_events
    WHERE event_type='completed' AND ts >= datetime('now', ?)
  `, [`-${days} days`]);
  const activeDays = Number(activeDaysRow?.[0]?.d || 0);

  const enoughData = activeDays >= minDays;

  const hoursMap = new Map();
  for (const r of completedByHour) {
    hoursMap.set(Number(r.hour), {
      completed: Number(r.completed || 0),
      p12: Number(r.p12 || 0),
      sent: 0,
      accepted: 0,
      ignored: 0,
      offCount: 0
    });
  }
  for (const r of reactionsByHour) {
    const h = Number(r.hour);
    const prev = hoursMap.get(h) || { completed: 0, p12: 0, sent: 0, accepted: 0, ignored: 0, offCount: 0 };
    prev.sent = Number(r.sent || 0);
    prev.accepted = Number(r.accepted || 0);
    prev.ignored = Number(r.ignored || 0);
    prev.offCount = Number(r.off_count || 0);
    hoursMap.set(h, prev);
  }

  const dayRows = queryAll(cfg.stateDir, `
    SELECT date,
           meetings_minutes,
           free_minutes,
           tasks_completed,
           tasks_overdue,
           (p1_completed + p2_completed) AS p12_completed
    FROM user_metrics_daily
    WHERE date >= date('now', ?)
    ORDER BY date DESC
  `, [`-${days} days`]);

  const profileByWeekday = queryAll(cfg.stateDir, `
    SELECT strftime('%w', date) AS wd,
           AVG(tasks_completed) AS avg_completed,
           AVG(meetings_minutes) AS avg_meetings,
           AVG(free_minutes) AS avg_free
    FROM user_metrics_daily
    WHERE date >= date('now', ?)
    GROUP BY wd
  `, [`-${days} days`]);

  if (!enoughData) {
    return {
      enoughData: false,
      message: "Недостаточно данных: пока учусь на вашем ритме.",
      activeDays,
      days,
      hourly: {},
      strongWindow: null,
      quickWindow: null,
      weakWindow: null,
      reminder: { preMin: 10, followupMin: 10, style: "normal", brutalOnlyP1: false },
      profileByWeekday,
      dayRows,
      generatedAt: new Date().toISOString(),
      today
    };
  }

  let strong = { h: 9, score: -1e9 };
  let weak = { h: 14, score: 1e9 };
  for (let h = 6; h <= 21; h += 1) {
    const s = scoreWindow(hoursMap, h);
    if (s > strong.score) strong = { h, score: s };
    if (s < weak.score) weak = { h, score: s };
  }

  const quickCandidates = [...hoursMap.entries()]
    .map(([h, r]) => ({ h, score: r.completed - Math.max(0, r.p12 - 1) * 0.5 }))
    .sort((a, b) => b.score - a.score);
  const quick = quickCandidates[0]?.h ?? Math.min(19, strong.h + 2);

  const totalSent = reactionsByHour.reduce((acc, r) => acc + Number(r.sent || 0), 0);
  const totalAccepted = reactionsByHour.reduce((acc, r) => acc + Number(r.accepted || 0), 0);
  const totalIgnored = reactionsByHour.reduce((acc, r) => acc + Number(r.ignored || 0), 0);
  const totalOff = reactionsByHour.reduce((acc, r) => acc + Number(r.off_count || 0), 0);

  const acceptedRate = totalSent ? totalAccepted / totalSent : 0;
  const ignoredRate = totalSent ? totalIgnored / totalSent : 0;

  const overdueRow = queryAll(cfg.stateDir, `
    SELECT SUM(tasks_overdue) AS overdue, SUM(tasks_completed) AS completed
    FROM user_metrics_daily
    WHERE date >= date('now', ?)
  `, [`-${days} days`])[0] || { overdue: 0, completed: 0 };

  const overdue = Number(overdueRow.overdue || 0);
  const completed = Number(overdueRow.completed || 0);
  const lateRatio = completed ? overdue / completed : 0;

  const preMin = lateRatio > 0.35 ? 15 : 10;
  const followupMin = ignoredRate > 0.45 ? 15 : 10;
  const style = totalOff >= 2 ? "soft" : (acceptedRate > 0.55 ? "normal" : "normal");
  const brutalOnlyP1 = totalOff === 0 && acceptedRate > 0.7;

  const hourly = {};
  for (let h = 6; h <= 23; h += 1) {
    const r = hoursMap.get(h) || { completed: 0, p12: 0, sent: 0, accepted: 0, ignored: 0, offCount: 0 };
    hourly[h] = {
      completed: r.completed,
      p12: r.p12,
      sent: r.sent,
      accepted: r.accepted,
      ignored: r.ignored,
      acceptRate: r.sent ? r.accepted / r.sent : null
    };
  }

  return {
    enoughData: true,
    message: null,
    activeDays,
    days,
    hourly,
    strongWindow: makeWindow(strong.h, 2),
    quickWindow: makeWindow(quick, 1),
    weakWindow: makeWindow(weak.h, 1),
    reminder: { preMin, followupMin, style, brutalOnlyP1 },
    profileByWeekday,
    dayRows,
    acceptedRate,
    ignoredRate,
    totalOff,
    generatedAt: new Date().toISOString(),
    today
  };
}
