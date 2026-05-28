import { getConfig } from "./config.mjs";
import { loadFocusBlocks, saveFocusBlocks } from "./productivity-state.mjs";
import { dateISOInTz } from "./time.mjs";
import { sendTelegramMessage } from "./telegram.mjs";

function hhmmNow(date, tz) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function toMin(v) {
  return Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5));
}

export async function runFocusTick(override = {}) {
  const cfg = { ...getConfig(), ...override };
  const sendFn = override.sendFn || (async (text) => {
    if (!cfg.telegramBotToken || !cfg.telegramOwnerId) return;
    await sendTelegramMessage(cfg.telegramBotToken, cfg.telegramOwnerId, text);
  });

  const now = new Date(Number(override.nowMs || Date.now()));
  const dateIso = dateISOInTz(now, cfg.tz);
  const hhmm = hhmmNow(now, cfg.tz);

  const st = loadFocusBlocks(cfg.stateDir);
  const entries = st.entries || [];
  let changed = false;
  let sent = 0;

  for (const b of entries) {
    if (b.date !== dateIso || b.status === "canceled") continue;

    const preTargetMin = toMin(b.start_time) - Number(cfg.focusPreNotifyMin || 5);
    const nowMin = toMin(hhmm);

    if (!b.pre_sent_at && nowMin >= preTargetMin && nowMin < toMin(b.start_time)) {
      await sendFn(`🧱 Через ${cfg.focusPreNotifyMin || 5} минут фокус-блок\n${b.start_time}–${b.end_time} — ${b.title}`);
      b.pre_sent_at = new Date().toISOString();
      changed = true;
      sent += 1;
    }

    if (!b.start_sent_at && nowMin >= toMin(b.start_time) && nowMin < toMin(b.end_time)) {
      await sendFn(`▶️ Старт фокус-блока\n${b.start_time}–${b.end_time} — ${b.title}\nНачинай.`);
      b.start_sent_at = new Date().toISOString();
      b.status = "active";
      changed = true;
      sent += 1;
    }

    if (!b.end_sent_at && nowMin >= toMin(b.end_time)) {
      await sendFn(`✅ Фокус-блок завершён\n${b.start_time}–${b.end_time} — ${b.title}\nЗакрыл задачу?`);
      b.end_sent_at = new Date().toISOString();
      b.status = "done";
      changed = true;
      sent += 1;
    }
  }

  if (changed) saveFocusBlocks(cfg.stateDir, st);
  return { dateIso, hhmm, sent };
}

async function main() {
  const r = await runFocusTick();
  console.log(`focus_tick date=${r.dateIso} time=${r.hhmm} sent=${r.sent}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
