import { formatHour } from './time.js';

function planText(requiredPerHour) {
  if (requiredPerHour > 1500) {
    return 'Нужен плотный план: одна длинная прогулка 45-60 минут и разбить остаток на 2 выхода.';
  }
  if (requiredPerHour >= 800) {
    return 'Реалистичный план: 2 выхода по 25-30 минут в удобные окна.';
  }
  return 'Лёгкий план: один короткий выход на 15-20 минут, и цель будет закрыта.';
}

function scenario(state, profile, goalSteps) {
  if (state.remainingSteps <= 1500) return 'D';
  if (state.forecast < goalSteps * 0.9) return 'C';

  const share15 = profile?.shareByHour?.[15] || 0;
  if (state.nowHourInt <= 15) {
    if (share15 < 0.4) return 'A';
    if (state.deviationFromProfile < -0.15) return 'B';
  }

  return 'BASE';
}

function scenarioText(kind, profile) {
  if (kind === 'A') {
    return `По твоему паттерну это норм: ты обычно разгоняешься после ${formatHour(profile?.typicalHalfDayHour || 18)}. Держим курс.`;
  }
  if (kind === 'B') {
    return 'Обычно к этому времени ты уже выше. Сегодня есть просадка, но её можно спокойно компенсировать.';
  }
  if (kind === 'C') {
    return 'Есть риск не добрать цель сегодня. Нужен конкретный план без откладывания.';
  }
  if (kind === 'D') {
    return 'Ты почти у цели. Добей сейчас короткой прогулкой и закроем день.';
  }
  return 'Держим стабильный темп и закрываем цель без рывков.';
}

export function buildStatusMessage(state, profile, goalSteps) {
  const kind = scenario(state, profile, goalSteps);
  const core = [
    `Шаги: ${state.nowSteps}/${goalSteps} (осталось ${state.remainingSteps}).`,
    `Прогноз на конец дня: ~${state.forecast}.`,
    `Нужно в среднем: ~${state.requiredPerHour} шаг/час до 23:00.`,
    scenarioText(kind, profile),
    planText(state.requiredPerHour),
  ];

  return {
    scenario: kind,
    text: core.join('\n'),
  };
}
