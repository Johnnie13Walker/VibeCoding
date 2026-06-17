import assert from "node:assert/strict";
import { rm } from "node:fs/promises";
import path from "node:path";
import { createBotModules } from "../src/index.js";
import { createMemoryTodoProvider } from "../src/providers/memoryTodoProvider.js";
import { toMoscowDateString } from "../src/time/moscowTime.js";

async function main() {
  const settingsFile = path.join(process.cwd(), "data", "smoke-settings.json");
  const notificationLogFile = path.join(
    process.cwd(),
    "data",
    "smoke-notification-log.json"
  );

  await rm(settingsFile, { force: true });
  await rm(notificationLogFile, { force: true });

  try {
    let nowTs = Date.UTC(2026, 2, 1, 9, 2, 0, 0); // 12:02 МСК
    const todoProvider = createMemoryTodoProvider([
      {
        id: "smoke-task-1",
        title: "Сверить план дня",
        dueDate: toMoscowDateString(nowTs),
        dueTime: "12:12",
        project: "Операционка",
        label: "Контроль",
        isClosed: false
      }
    ]);

    const env = {
      TELEGRAM_OWNER_ID: "100500",
      SETTINGS_FILE: settingsFile,
      NOTIFICATION_LOG_FILE: notificationLogFile
    };

    const modules = createBotModules(env, console, {
      todoProvider,
      now: () => nowTs
    });

    const outbox = [];
    const sendMessage = async (msg) => outbox.push(msg.text);

    const tMinus = await modules.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(tMinus.sent.length, 1);
    assert.match(outbox[0], /Через 10 минут/);

    const dedup = await modules.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(dedup.sent.length, 0);

    nowTs = Date.UTC(2026, 2, 1, 9, 12, 0, 0); // 12:12 МСК
    const exact = await modules.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(exact.sent.length, 1);
    assert.match(outbox[1], /Коротко: делай/);

    console.log("SMOKE NOTIFICATIONS OK");
    console.log(outbox.join("\n---\n"));
  } finally {
    await rm(settingsFile, { force: true });
    await rm(notificationLogFile, { force: true });
  }
}

main().catch((error) => {
  console.error("SMOKE NOTIFICATIONS FAIL", error);
  process.exit(1);
});
