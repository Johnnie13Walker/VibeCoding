function pickByPriority(tasks, maxPriority = 4) {
  return (tasks || []).filter((t) => Number(t.displayPriority || 4) <= maxPriority);
}

function pickQuick(tasks) {
  return (tasks || []).filter((t) => Number(t.etaMin || 999) <= 35);
}

function pickDeep(tasks) {
  return (tasks || []).filter((t) => Number(t.displayPriority || 4) <= 2 && Number(t.etaMin || 0) >= 40);
}

function uniqueByTitle(tasks) {
  const out = [];
  const seen = new Set();
  for (const t of tasks || []) {
    const k = String(t.title || t.content || "").toLowerCase().trim();
    if (!k || seen.has(k)) continue;
    seen.add(k);
    out.push(t);
  }
  return out;
}

function pickTask(tasks) {
  return uniqueByTitle(tasks)[0] || null;
}

export function getNextBestAction(now, context, cfg = {}) {
  if (!context || context.inMeeting) {
    return { kind: "none", reason: "in_meeting", task: null, text: "" };
  }

  const tasks = context.tasks || [];
  if (!tasks.length) {
    return { kind: "none", reason: "no_tasks", task: null, text: "" };
  }

  const minsToMeeting = context.minutesToNextMeeting;
  const freeMin = Number(context.freeUntilNextMeeting || 0);

  let selected = null;
  let reason = "default";

  if (minsToMeeting != null && minsToMeeting < 20) {
    selected = pickTask(pickQuick(pickByPriority(tasks, 3)));
    reason = "before_meeting_quick";
  }

  if (!selected && freeMin > 60) {
    selected = pickTask(pickDeep(tasks)) || pickTask(pickByPriority(tasks, 2));
    reason = "deep_window";
  }

  if (!selected && freeMin >= 20 && freeMin <= 40) {
    selected = pickTask(pickQuick(pickByPriority(tasks, 3)));
    reason = "short_window";
  }

  if (!selected && freeMin > 0) {
    selected = pickTask(pickByPriority(tasks, 3));
    reason = "standard_window";
  }

  if (!selected) {
    return { kind: "none", reason: "no_fit", task: null, text: "" };
  }

  const lines = [];
  if (context.overloaded) {
    lines.push("⚠️ Сегодня плотный график.");
    lines.push("Свободного времени мало — фокус на 1 задаче.");
    lines.push("");
  } else if (freeMin >= 45) {
    lines.push("💡 Сейчас хорошее окно для важной задачи.");
    lines.push("");
  }

  lines.push("🧠 Сейчас лучший фокус:");
  lines.push(`• ${selected.title || selected.content || "Задача"}`);
  if (minsToMeeting != null && minsToMeeting > 0) {
    lines.push(`(до следующей встречи ${minsToMeeting} минут)`);
  }

  return {
    kind: "next_action",
    reason,
    task: selected,
    key: `${selected.id || "x"}:${selected.title || selected.content || ""}:${reason}`,
    text: lines.join("\n")
  };
}
