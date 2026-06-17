import { buildRhythmModel } from "./rhythmModel.mjs";
import { isProfileEnabled } from "./storage.mjs";

function pct(a, b) {
  if (!b) return "0%";
  return `${Math.round((a / b) * 100)}%`;
}

function classifyDayType(row) {
  const m = Number(row.meetings_minutes || 0);
  const f = Number(row.free_minutes || 0);
  if (m >= 300) return "meeting-heavy";
  if (f >= 240 && m <= 120) return "deep-work";
  if (m >= 240 && f < 120) return "overloaded";
  return "hybrid";
}

export function formatMeInsights(cfg) {
  const enabled = isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false);
  if (!enabled) {
    return "Профиль: OFF\nВключите /profile on, чтобы собирать персональные инсайты.";
  }

  const m14 = buildRhythmModel(cfg, { days: 14, minDays: 4 });
  const m30 = buildRhythmModel(cfg, { days: 30, minDays: 7 });

  if (!m30.enoughData) {
    return [
      "👤 /me",
      "Недостаточно данных: пока учусь на вашем ритме.",
      `Набрано активных дней: ${m30.activeDays}/7`
    ].join("\n");
  }

  const dayTypes = { "meeting-heavy": 0, "deep-work": 0, hybrid: 0, overloaded: 0 };
  for (const r of m30.dayRows || []) dayTypes[classifyDayType(r)] += 1;
  const mainDayType = Object.entries(dayTypes).sort((a, b) => b[1] - a[1])[0]?.[0] || "hybrid";

  const p12Done = (m30.dayRows || []).reduce((acc, x) => acc + Number(x.p12_completed || 0), 0);
  const allDone = (m30.dayRows || []).reduce((acc, x) => acc + Number(x.tasks_completed || 0), 0);

  let rootCause = "нет фокуса";
  const avgMeetings = (m30.dayRows || []).reduce((acc, x) => acc + Number(x.meetings_minutes || 0), 0) / Math.max(1, (m30.dayRows || []).length);
  const noDue = (m30.dayRows || []).filter((x) => Number(x.tasks_completed || 0) === 0 && Number(x.tasks_overdue || 0) > 0).length;
  if (avgMeetings >= 280) rootCause = "перегруз встречами";
  else if (noDue >= 3) rootCause = "слишком много задач без срока";

  return [
    "👤 /me (14/30 дней)",
    `Топ-окна продуктивности: ${m30.strongWindow}, ${m30.quickWindow}`,
    `Провальное окно: ${m30.weakWindow}`,
    `Тип дня чаще всего: ${mainDayType}`,
    `Закрытие приоритета 1–2: ${pct(p12Done, allDone)}`,
    `Главная причина провалов: ${rootCause}`,
    `Реакция на подсказки: accepted ${pct(m30.acceptedRate || 0, 1)}, ignored ${pct(m30.ignoredRate || 0, 1)}`
  ].join("\n");
}
