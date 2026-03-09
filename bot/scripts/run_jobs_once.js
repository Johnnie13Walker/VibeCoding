import { createBotModules } from "../src/index.js";
import { createTelegramTransport } from "../src/services/telegramTransport.js";

function readTargets(env) {
  const userId = String(env.TELEGRAM_OWNER_ID || env.JOBS_USER_ID || "");
  const chatId = String(env.TELEGRAM_CHAT_ID || env.JOBS_CHAT_ID || "");
  if (!userId || !chatId) {
    throw new Error("Не заданы TELEGRAM_OWNER_ID/TELEGRAM_CHAT_ID (или JOBS_USER_ID/JOBS_CHAT_ID)");
  }
  return { userId, chatId };
}

async function main() {
  const env = process.env;
  const { userId, chatId } = readTargets(env);
  const modules = createBotModules(env);
  const telegram = createTelegramTransport({ env });

  const sent = [];
  const sendMessage = async (message) => {
    // Пишем в stdout и отправляем в Telegram (или dry-run при TELEGRAM_DRY_RUN=1).
    sent.push(message);
    console.log(`\n[OUTBOX:${message.triggerType}]`);
    console.log(message.text);
    await telegram.send(message);
  };

  const timeRun = await modules.taskTimeNotificationsJob.run({
    userId,
    chatId,
    sendMessage
  });

  const eveningRun = await modules.eveningReminderJob.run({
    userId,
    chatId,
    sendMessage
  });

  console.log("\nRUN SUMMARY", JSON.stringify({
    task_time_notifications: { status: timeRun.status, sent: timeRun.sent?.length || 0 },
    evening_reminder: { status: eveningRun.status, sent: Boolean(eveningRun.sent) },
    totalMessages: sent.length
  }));
}

main().catch((error) => {
  console.error("RUN JOBS ONCE FAIL", error);
  process.exit(1);
});
