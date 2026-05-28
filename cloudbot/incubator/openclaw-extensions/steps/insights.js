import { formatHour, formatHourWindow } from './time.js';

function mean(values) {
  if (!values.length) return 0;
  const sum = values.reduce((a, b) => a + b, 0);
  return Math.round(sum / values.length);
}

function dailyTotals(dayProfiles) {
  return dayProfiles.map((d) => d.total).filter((x) => Number.isFinite(x) && x > 0);
}

function profileText(profile) {
  const checkpoints = [10, 15, 20];
  return checkpoints
    .map((h) => `к ${formatHour(h)} ~${Math.round((profile.shareByHour[h] || 0) * 100)}%`)
    .join(', ');
}

function topPeakWindows(profile) {
  return (profile.peakWindows || []).map((w) => w.windowLabel || formatHourWindow(w.hour));
}

export function buildInsights(profile, goalSteps) {
  const totals = dailyTotals(profile.dayProfiles || []);
  const avg7 = mean(totals.slice(-7));
  const closed14 = totals.slice(-14).filter((x) => x >= goalSteps).length;
  const peaks = topPeakWindows(profile).slice(0, 2);

  const lines = [
    `Средний итог за 7 дней: ${avg7} шагов.`,
    `Пиковые окна активности: ${peaks.join(' и ') || 'недостаточно данных'}.`,
    `Цель закрыта за 14 дней: ${closed14} дн.`,
    `Профиль дня: ${profileText(profile)}.`,
  ];

  return {
    avg7,
    closed14,
    peaks,
    profileSummary: profileText(profile),
    text: lines.join('\n'),
  };
}
