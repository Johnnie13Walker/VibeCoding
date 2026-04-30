import { buildRhythmModel } from "./rhythmModel.mjs";
import { isProfileEnabled } from "./storage.mjs";

function parseHourFromHHMM(v) {
  const m = String(v || "").match(/^(\d{2}):/);
  return m ? Number(m[1]) : null;
}

function taskTitle(t) {
  return String(t?.title || t?.content || "Задача").trim() || "Задача";
}

export function getPersonalizationSnapshot(cfg) {
  const enabled = isProfileEnabled(cfg.stateDir, cfg.profileEnabledDefault !== false);
  if (!enabled) {
    return {
      enabled: false,
      enoughData: false,
      message: "Профиль выключен.",
      reminder: { preMin: cfg.taskReminderPreMin, followupMin: cfg.taskReminderFollowupMin, style: cfg.reminderStyle, brutalOnlyP1: false }
    };
  }
  const model = buildRhythmModel(cfg, { days: 30, minDays: 7 });
  return { enabled: true, ...model };
}

export function buildRhythmBlock(snapshot) {
  if (!snapshot) return [];
  if (!snapshot?.enabled) {
    return ["⚡ Мой ритм (сегодня)", "Профиль персонализации выключен."];
  }
  if (!snapshot.enoughData) {
    return ["⚡ Мой ритм (сегодня)", "Недостаточно данных: пока учусь на вашем ритме."];
  }
  return [
    "⚡ Мой ритм (сегодня)",
    `лучшее окно для сложных задач: ${snapshot.strongWindow}`,
    `лучшее окно для быстрых задач: ${snapshot.quickWindow}`,
    `опасное окно: ${snapshot.weakWindow}`
  ];
}

export function getExecutionCooldownMultiplier(snapshot, hour) {
  if (!snapshot?.enabled || !snapshot?.enoughData) return 1;
  const h = Number(hour);
  const row = snapshot.hourly?.[h];
  if (!row) return 1;
  if (row.sent >= 4 && row.acceptRate != null && row.acceptRate < 0.2) return 1.8;
  return 1;
}

export function adaptNextActionByRhythm(action, context, snapshot) {
  if (!action || action.kind !== "next_action") return action;
  if (!snapshot?.enabled || !snapshot?.enoughData) return action;

  const hour = parseHourFromHHMM(context?.nowHHMM || "");
  if (hour == null) return action;

  const weakStart = parseHourFromHHMM(snapshot.weakWindow);
  const strongStart = parseHourFromHHMM(snapshot.strongWindow);

  const tasks = context.tasks || [];

  if (weakStart != null && hour === weakStart) {
    const easy = tasks.find((t) => Number(t.etaMin || 999) <= 30 && Number(t.displayPriority || 4) <= 3);
    if (easy) {
      return {
        ...action,
        task: easy,
        key: `${easy.id || "x"}:${taskTitle(easy)}:weak_hour`,
        text: [
          "🧠 Сейчас лучший фокус:",
          `• ${taskTitle(easy)}`,
          "(лёгкий шаг под ваш текущий ритм)"
        ].join("\n")
      };
    }
  }

  if (strongStart != null && (hour === strongStart || hour === strongStart + 1)) {
    const hard = tasks.find((t) => Number(t.displayPriority || 4) <= 2 && Number(t.etaMin || 0) >= 40);
    if (hard) {
      return {
        ...action,
        task: hard,
        key: `${hard.id || "x"}:${taskTitle(hard)}:strong_hour`,
        text: [
          "💡 Ваш сильный час.",
          "🧠 Сейчас лучший фокус:",
          `• ${taskTitle(hard)}`
        ].join("\n")
      };
    }
  }

  return action;
}

export function adaptReminderParams(snapshot, base, meta = {}) {
  const out = {
    preMin: Number(base.preMin || 10),
    followupMin: Number(base.followupMin || 10),
    style: String(base.style || "normal"),
    brutalOnlyP1: false
  };

  if (!snapshot?.enabled || !snapshot?.enoughData) return out;

  out.preMin = Number(snapshot.reminder?.preMin || out.preMin);
  out.followupMin = Number(snapshot.reminder?.followupMin || out.followupMin);
  out.style = String(snapshot.reminder?.style || out.style);
  out.brutalOnlyP1 = !!snapshot.reminder?.brutalOnlyP1;

  if (out.brutalOnlyP1 && Number(meta.displayPriority || 3) > 1 && out.style === "brutal") {
    out.style = "normal";
  }

  return out;
}
