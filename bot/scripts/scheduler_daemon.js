import { createBotModules } from "../src/index.js";
import { createDaemonScheduler } from "../src/scheduler/daemonScheduler.js";
import { createTelegramTransport } from "../src/services/telegramTransport.js";
import {
  buildTelegramRoutingConfig,
  resolveTelegramChatId
} from "../src/services/telegramTargets.js";

function resolveTarget(env) {
  const routing = buildTelegramRoutingConfig(env);
  const userId = String(env.TELEGRAM_OWNER_ID || env.JOBS_USER_ID || "").trim();
  const chatId = resolveTelegramChatId({
    chatId: String(env.JOBS_CHAT_ID || env.TELEGRAM_CHAT_ID || "").trim(),
    chatAlias: String(env.JOBS_CHAT_ALIAS || env.TELEGRAM_DEFAULT_CHAT_ALIAS || "").trim(),
    defaultChatId: routing.defaultChatId,
    targets: routing.targets,
    allowedChatIds: routing.allowedChatIds
  });
  if (!userId || !chatId) {
    throw new Error(
      "Не заданы TELEGRAM_OWNER_ID и Telegram target (TELEGRAM_CHAT_ID, TELEGRAM_TARGETS + JOBS_CHAT_ALIAS или JOBS_CHAT_ID)"
    );
  }
  return { userId, chatId };
}

async function main() {
  const env = process.env;
  const target = resolveTarget(env);

  const modules = createBotModules(env);
  const telegram = createTelegramTransport({ env });

  const scheduler = createDaemonScheduler({
    jobs: modules.schedulerJobs,
    target,
    sendMessage: (message) => telegram.send(message),
    logger: console
  });

  scheduler.start();

  process.on("SIGINT", () => {
    scheduler.stop();
    process.exit(0);
  });

  process.on("SIGTERM", () => {
    scheduler.stop();
    process.exit(0);
  });
}

main().catch((error) => {
  console.error("SCHEDULER DAEMON FAIL", error);
  process.exit(1);
});
