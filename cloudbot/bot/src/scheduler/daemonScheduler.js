import { getMoscowParts, MOSCOW_TZ } from "../time/moscowTime.js";

function parseField(field, value, min, max) {
  if (field === "*") return true;
  if (/^\*\/\d+$/.test(field)) {
    const step = Number(field.slice(2));
    return step > 0 && value % step === 0;
  }
  if (/^\d+$/.test(field)) {
    const num = Number(field);
    return num >= min && num <= max && num === value;
  }
  return false;
}

function isJobDue(schedule, timestampMs) {
  const parts = String(schedule || "").trim().split(/\s+/);
  if (parts.length !== 5) return false;

  const [minuteField, hourField] = parts;
  const msk = getMoscowParts(timestampMs);
  return (
    parseField(minuteField, msk.minute, 0, 59) &&
    parseField(hourField, msk.hour, 0, 23)
  );
}

function minuteBucket(timestampMs) {
  return Math.floor(timestampMs / 60000);
}

export function createDaemonScheduler({ jobs, target, sendMessage, now = () => Date.now(), logger = console }) {
  let timer = null;
  const lastRunByJob = new Map();

  async function tick() {
    const ts = now();
    const bucket = minuteBucket(ts);

    for (const job of jobs) {
      if (!isJobDue(job.schedule, ts)) continue;
      if (lastRunByJob.get(job.name) === bucket) continue;

      lastRunByJob.set(job.name, bucket);
      try {
        const result = await job.run({
          userId: target.userId,
          chatId: target.chatId,
          sendMessage
        });
        logger.info?.(`[scheduler] ${job.name} ${JSON.stringify(result || {})}`);
      } catch (error) {
        logger.error?.(`[scheduler] ${job.name} failed`, error);
      }
    }
  }

  function start() {
    if (timer) return;
    logger.info?.(`[scheduler] start tz=${MOSCOW_TZ} jobs=${jobs.map((j) => j.name).join(",")}`);
    tick();
    timer = setInterval(tick, 60 * 1000);
  }

  function stop() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
    logger.info?.("[scheduler] stopped");
  }

  return { start, stop, tick };
}
