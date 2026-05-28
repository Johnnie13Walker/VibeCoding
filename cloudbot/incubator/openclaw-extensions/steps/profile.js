import { dayKey, hourInt, formatHourWindow } from './time.js';

const START_HOUR = 6;
const END_HOUR = 23;

function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

function groupByDay(events, timeZone) {
  const map = new Map();
  for (const ev of events) {
    const d = new Date(ev.ts);
    const key = dayKey(d, timeZone);
    const list = map.get(key) || [];
    list.push({
      ts: d,
      stepsToday: Number(ev.stepsToday) || 0,
      hour: hourInt(d, timeZone),
    });
    map.set(key, list);
  }
  return map;
}

function daySeries(points) {
  const sorted = [...points].sort((a, b) => a.ts - b.ts);
  let total = 0;
  for (const p of sorted) total = Math.max(total, p.stepsToday);
  if (total <= 0) return null;

  const cumulativeByHour = {};
  let cursor = 0;
  let current = 0;
  for (let h = START_HOUR; h <= END_HOUR; h += 1) {
    while (cursor < sorted.length && sorted[cursor].hour <= h) {
      current = Math.max(current, sorted[cursor].stepsToday);
      cursor += 1;
    }
    cumulativeByHour[h] = current;
  }

  const shareByHour = {};
  for (let h = START_HOUR; h <= END_HOUR; h += 1) {
    shareByHour[h] = Math.min(1, Math.max(0, cumulativeByHour[h] / total));
  }

  return { total, cumulativeByHour, shareByHour };
}

function topPeakWindows(shareByHour) {
  const growth = [];
  let prev = 0;
  for (let h = START_HOUR; h <= END_HOUR; h += 1) {
    const cur = shareByHour[h] || 0;
    const delta = Math.max(0, cur - prev);
    growth.push({ hour: h, delta });
    prev = cur;
  }
  growth.sort((a, b) => b.delta - a.delta);
  return growth.slice(0, 2).map((x) => ({
    hour: x.hour,
    shareDelta: x.delta,
    windowLabel: formatHourWindow(x.hour),
  }));
}

export function buildActivityProfile(events, {
  now = new Date(),
  timeZone = 'Europe/Moscow',
  lookbackDays = 14,
  minDays = 7,
} = {}) {
  const todayKey = dayKey(now, timeZone);
  const earliestMs = now.getTime() - lookbackDays * 24 * 60 * 60 * 1000;
  const recent = events.filter((e) => Date.parse(e.ts) >= earliestMs);
  const grouped = groupByDay(recent, timeZone);

  const dayKeys = [...grouped.keys()]
    .filter((d) => d !== todayKey)
    .sort()
    .slice(-lookbackDays);

  const dayProfiles = [];
  for (const d of dayKeys) {
    const s = daySeries(grouped.get(d) || []);
    if (s) dayProfiles.push({ day: d, ...s });
  }

  const shareByHour = {};
  for (let h = START_HOUR; h <= END_HOUR; h += 1) {
    const samples = dayProfiles.map((x) => x.shareByHour[h]).filter((x) => Number.isFinite(x));
    shareByHour[h] = median(samples);
  }

  const peakWindows = topPeakWindows(shareByHour);
  const typicalHalfDayHour = (() => {
    for (let h = START_HOUR; h <= END_HOUR; h += 1) {
      if ((shareByHour[h] || 0) >= 0.5) return h;
    }
    return 20;
  })();

  return {
    daysUsed: dayProfiles.length,
    minDays,
    isReliableByDays: dayProfiles.length >= minDays,
    startHour: START_HOUR,
    endHour: END_HOUR,
    shareByHour,
    peakWindows,
    typicalHalfDayHour,
    dayProfiles,
  };
}
