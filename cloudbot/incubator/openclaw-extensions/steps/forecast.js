import { dayKey, hourFloat, hourInt } from './time.js';

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function currentDayPoints(events, now, timeZone) {
  const today = dayKey(now, timeZone);
  return events
    .filter((e) => dayKey(new Date(e.ts), timeZone) === today)
    .map((e) => ({ ts: new Date(e.ts), stepsToday: Number(e.stepsToday) || 0 }))
    .sort((a, b) => a.ts - b.ts);
}

function stepsNow(points) {
  let max = 0;
  for (const p of points) max = Math.max(max, p.stepsToday);
  return max;
}

function measurementReliability(points, nowHourInt, timeZone) {
  if (points.length >= 2) return true;
  return points.some((p) => hourInt(p.ts, timeZone) >= 10);
}

function linearForecast(steps, nowHourFloat) {
  if (nowHourFloat >= 23) return steps;
  const elapsed = Math.max(0.5, nowHourFloat - 6);
  const full = 17;
  const pace = steps / elapsed;
  return Math.max(steps, Math.round(pace * full));
}

function profileShareAtHour(profile, hour) {
  if (!profile?.shareByHour) return 0;
  const h = clamp(hour, profile.startHour || 6, profile.endHour || 23);
  return Number(profile.shareByHour[h] || 0);
}

function profileForecast(steps, shareNow) {
  const safeShare = clamp(shareNow, 0.05, 0.98);
  return Math.max(steps, Math.round(steps / safeShare));
}

export function computeStepState(events, profile, {
  now = new Date(),
  timeZone = 'Europe/Moscow',
  goalSteps = 10000,
} = {}) {
  const pointsToday = currentDayPoints(events, now, timeZone);
  const nowHourFloat = hourFloat(now, timeZone);
  const nowHourInt = Math.floor(nowHourFloat);
  const nowSteps = stepsNow(pointsToday);

  const shareNow = profileShareAtHour(profile, nowHourInt);
  const reliableProfile = Boolean(
    profile?.isReliableByDays
      && measurementReliability(pointsToday, nowHourInt, timeZone)
      && shareNow > 0
  );

  const forecastLinear = linearForecast(nowSteps, nowHourFloat);
  const forecastProfile = profileForecast(nowSteps, shareNow || 0.1);
  const forecast = reliableProfile
    ? Math.round(0.7 * forecastProfile + 0.3 * forecastLinear)
    : forecastLinear;

  const remainingSteps = Math.max(goalSteps - nowSteps, 0);
  const remainingHours = Math.max(0.25, 23 - nowHourFloat);
  const requiredPerHour = Math.round(remainingSteps / remainingHours);

  const expectedAtGoalNow = Math.round(goalSteps * shareNow);
  const deviationFromProfile = expectedAtGoalNow > 0
    ? (nowSteps - expectedAtGoalNow) / expectedAtGoalNow
    : 0;

  return {
    now,
    nowSteps,
    nowHourInt,
    nowHourFloat,
    pointsToday,
    shareNow,
    reliableProfile,
    forecastLinear,
    forecastProfile,
    forecast,
    remainingSteps,
    remainingHours,
    requiredPerHour,
    expectedAtGoalNow,
    deviationFromProfile,
  };
}
