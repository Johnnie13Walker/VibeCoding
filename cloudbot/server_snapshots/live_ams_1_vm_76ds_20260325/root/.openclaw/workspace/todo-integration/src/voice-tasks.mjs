import { parseAddDraft } from "./add-parser.mjs";

const BATCH_MARKERS = [
  /потом/i,
  /и\s+еще/i,
  /и\s+ещ[её]/i,
  /дальше/i,
  /первое/i,
  /второе/i,
  /третье/i,
  /четвертое/i,
  /пятое/i,
  /задачи\s*:/i
];

function normalize(s = "") {
  return String(s)
    .replace(/\s+/g, " ")
    .replace(/[\u2013\u2014]/g, "-")
    .trim();
}

function stripLeadingNoise(text) {
  return normalize(text)
    .replace(/^\s*(так|ну|ладно|короче|запиши)\s*[,:-]?\s*/i, "")
    .replace(/^\s*(добавь|добавить|задача|todo|поставь|напомни)\s*:?\s*/i, "")
    .replace(/^\s*задачи\s*[:,-]?\s*/i, "");
}

function stripJoinWords(part) {
  return normalize(
    part
      .replace(/^\s*(и|а|потом|дальше)\s+/i, "")
      .replace(/^[,.;:\-]+\s*/, "")
  );
}

export function looksLikeVoiceBatch(text) {
  const t = normalize(text);
  return BATCH_MARKERS.some((rx) => rx.test(t));
}

export function splitVoiceTasks(text) {
  const cleaned = stripLeadingNoise(text);
  if (!cleaned) return [];

  let work = ` ${cleaned} `;

  work = work.replace(/(первое|второе|третье|четвертое|пятое)/gi, " ||| ");
  work = work.replace(/(потом|и\s+еще|и\s+ещ[её]|дальше)/gi, " ||| ");
  work = work.replace(/[;\n]+/g, " ||| ");
  work = work.replace(/\s{2,}/g, " ");

  const parts = work
    .split("|||")
    .map((p) => stripJoinWords(p))
    .filter(Boolean);

  return parts.length ? parts : [cleaned];
}

export function parseVoiceTasks(transcript, tz, maxTasks = 30) {
  const chunks = splitVoiceTasks(transcript);
  const source = chunks.length ? chunks : [normalize(transcript)];

  const tasks = [];
  for (const chunk of source) {
    const draft = parseAddDraft(chunk, tz);
    if (!draft.content) continue;
    tasks.push({
      content: draft.content.replace(/^\s*задач[ауеы]\s+/i, "").replace(/[\s,.;:]+$/g, ""),
      dueDate: draft.dueDate,
      dueDateTime: draft.dueDateTime,
      pendingTime: draft.parsed.timeToken || null,
      needDateClarify: draft.needDateClarify
    });
    if (tasks.length >= maxTasks) break;
  }

  const unresolvedIndexes = [];
  tasks.forEach((t, idx) => {
    if (!t.dueDate && !t.dueDateTime) unresolvedIndexes.push(idx);
  });

  const lowConfidence =
    transcript.length < 18 ||
    /(ээ+|мм+|ну\s+вот|неразборчиво)/i.test(transcript) ||
    tasks.some((t) => t.content.split(/\s+/).length < 2);

  return {
    transcript: normalize(transcript),
    tasks,
    unresolvedIndexes,
    lowConfidence,
    truncated: source.length > maxTasks
  };
}
