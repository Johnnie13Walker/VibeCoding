const PRIORITY_TO_TODOIST = {
  P1: 4,
  P2: 3,
  P3: 2,
  P4: 1
};

const PRIORITY_EMOJI = {
  P1: "🔥",
  P2: "⚡",
  P3: "•",
  P4: "🧊"
};

const RULES = {
  P1: [
    /очень\s+срочно/i,
    /срочно/i,
    /горит/i,
    /критично/i,
    /\basap\b/i,
    /немедленно/i,
    /сегодня\s+обязательно/i
  ],
  P2: [
    /важно/i,
    /приоритет/i,
    /желательно\s+сегодня/i,
    /надо\s+сегодня/i,
    /до\s+конца\s+дня/i,
    /дедлайн/i
  ],
  P4: [
    /когда\s+будет\s+время/i,
    /не\s+срочно/i,
    /необязательно/i,
    /на\s+будущее/i,
    /потом/i
  ]
};

const CLEANUP_PATTERNS = [
  ...RULES.P4,
  ...RULES.P1,
  ...RULES.P2,
  /priority\s*[1-4]/i,
  /приоритет\s*[1-4]/i,
  /приоритет\s+(высокий|обычный|низкий|срочный|срочно)/i
];

function normalizeWhitespace(s = "") {
  return String(s).replace(/\s+/g, " ").trim();
}

function cleanupContent(text) {
  let out = String(text || "");
  for (const rx of CLEANUP_PATTERNS) {
    out = out.replace(rx, " ");
  }
  return normalizeWhitespace(out.replace(/^[\s,.;:]+/, "").replace(/^(но|и)\s+/i, "").replace(/[\s,.;:]+$/g, ""));
}

function countMatches(text, rules) {
  let count = 0;
  for (const rx of rules) {
    if (rx.test(text)) count += 1;
  }
  return count;
}

export function parsePriorityOverride(text) {
  const t = String(text || "").trim().toLowerCase();
  const num = t.match(/(?:^|\s)(?:priority|приоритет)\s*([1-4])(?:\s|$)/i) || t.match(/^([1-4])$/);
  if (num) return `P${num[1]}`;

  if (/сделай\s+приоритет\s*(срочно|высокий)/i.test(t)) {
    return /срочно/i.test(t) ? "P1" : "P2";
  }
  if (/приоритет\s*(срочно|срочный|очень\s+срочно|критично)/i.test(t)) return "P1";
  if (/приоритет\s*высок/i.test(t)) return "P2";
  if (/приоритет\s*(обычный|нормальный|средний)/i.test(t)) return "P3";
  if (/приоритет\s*низк/i.test(t)) return "P4";
  return null;
}

export function priorityToTodoist(priority = "P3") {
  return PRIORITY_TO_TODOIST[priority] || PRIORITY_TO_TODOIST.P3;
}

export function priorityLabel(priority = "P3") {
  return `${PRIORITY_EMOJI[priority] || "•"} ${priority}`;
}

export function detectPriority(content, cfg) {
  const source = normalizeWhitespace(content);
  const cleaned = cleanupContent(source) || source;

  const manual = parsePriorityOverride(source);
  if (manual) {
    return {
      priority: manual,
      todoistPriority: priorityToTodoist(manual),
      confidence: 1,
      needsClarify: false,
      reason: "manual",
      content: cleaned
    };
  }

  if (!cfg.autoPriorityEnabled) {
    return {
      priority: "P3",
      todoistPriority: priorityToTodoist("P3"),
      confidence: 1,
      needsClarify: false,
      reason: "disabled",
      content: cleaned
    };
  }

  const text = source.toLowerCase();
  const lowCount = countMatches(text, RULES.P4);
  const textWithoutLow = lowCount
    ? text.replace(/не\s+срочно|когда\s+будет\s+время|необязательно|на\s+будущее|потом/gi, " ")
    : text;
  const p1Count = countMatches(textWithoutLow, RULES.P1);
  const p2Count = countMatches(textWithoutLow, RULES.P2);

  const candidates = [
    ["P1", p1Count],
    ["P2", p2Count],
    ["P4", lowCount]
  ].filter(([, n]) => n > 0);

  if (!candidates.length) {
    return {
      priority: "P3",
      todoistPriority: priorityToTodoist("P3"),
      confidence: 0.95,
      needsClarify: false,
      reason: "default",
      content: cleaned
    };
  }

  candidates.sort((a, b) => b[1] - a[1]);
  const [topPriority, topCount] = candidates[0];
  const secondCount = candidates[1]?.[1] || 0;

  const conflict = secondCount > 0 && topCount === secondCount;
  let confidence = Math.min(0.98, 0.7 + topCount * 0.15 - secondCount * 0.1);
  if (conflict) confidence = Math.min(confidence, 0.45);

  return {
    priority: topPriority,
    todoistPriority: priorityToTodoist(topPriority),
    confidence,
    needsClarify: conflict || confidence < cfg.priorityConfidenceThreshold,
    reason: conflict ? "conflict" : "rule",
    content: cleaned
  };
}

export function priorityHelpText() {
  return [
    "Приоритеты задач:",
    "1 — 🔥 срочно (P1)",
    "2 — ⚡ высокий (P2)",
    "3 — • обычный (P3)",
    "4 — 🧊 низкий (P4)",
    "",
    "Примеры:",
    "• «срочно отправить договор» -> P1",
    "• «важно до конца дня» -> P2",
    "• «когда будет время почитать статью» -> P4"
  ].join("\n");
}
