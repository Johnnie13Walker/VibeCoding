import assert from "node:assert/strict";
import { rm, readFile } from "node:fs/promises";
import path from "node:path";
import { createBotModules } from "../src/index.js";
import { createMemoryTodoProvider } from "../src/providers/memoryTodoProvider.js";
import { createTelegramTransport } from "../src/services/telegramTransport.js";
import { toMoscowDateString } from "../src/time/moscowTime.js";

async function run() {
  const cacheFile = path.join(process.cwd(), "data", "users-cache.test.json");
  const settingsFile = path.join(process.cwd(), "data", "user-settings.test.json");
  const notificationLogFile = path.join(
    process.cwd(),
    "data",
    "notification-log.test.json"
  );

  await rm(cacheFile, { force: true });
  await rm(settingsFile, { force: true });
  await rm(notificationLogFile, { force: true });

  try {
    const env = {
      USE_FIXTURE_USERS: "1",
      TELEGRAM_OWNER_ID: "100500",
      USERS_CACHE_FILE: cacheFile,
      USERS_CACHE_TTL_MS: String(24 * 60 * 60 * 1000),
      SETTINGS_FILE: settingsFile,
      NOTIFICATION_LOG_FILE: notificationLogFile,
      NOTIFICATION_LOG_TTL_MS: String(7 * 24 * 60 * 60 * 1000)
    };

    const modules = createBotModules(env);

    // 1) "встреча с Петром" -> multiple -> выбор "1" -> ask_date
    const state1 = { step: "ask_attendees", payload: {} };
    const r1 = await modules.handleMeetCreateAttendee({
      state: state1,
      text: "встреча с Петром"
    });

    assert.equal(r1.state.step, "pick_attendee");
    assert.ok(Array.isArray(r1.state.payload.candidates));
    assert.ok(r1.state.payload.candidates.length >= 2);

    const r2 = modules.handlePickAttendee({ state: r1.state, text: "1" });
    assert.equal(r2.state.step, "ask_date");
    assert.equal(r2.state.payload.attendeeIds.length, 1);

    // 2) "встреча с несуществующим" -> none -> ask_attendees
    const state2 = { step: "ask_attendees", payload: {} };
    const r3 = await modules.handleMeetCreateAttendee({
      state: state2,
      text: "встреча с несуществующим"
    });

    assert.equal(r3.state.step, "ask_attendees");
    assert.match(r3.response.text, /Не нашел|Не нашел такого сотрудника/i);

    // 3) "обнови сотрудников" -> cache updated
    const sync = await modules.handleSyncUsersCommand({
      text: "обнови сотрудников",
      userId: "100500"
    });
    assert.match(sync.text, /Кэш сотрудников обновлен/i);

    const cacheRaw = JSON.parse(await readFile(cacheFile, "utf-8"));
    assert.ok(Array.isArray(cacheRaw.users));
    assert.ok(cacheRaw.users.length >= 5);

    // Проверка фильтра: уволенные/неактивные не попали
    const ids = new Set(cacheRaw.users.map((u) => String(u.id)));
    assert.equal(ids.has("106"), false);
    assert.equal(ids.has("107"), false);

    // 4) Команды уведомлений
    const status1 = await modules.handleNotificationSettingsCommand({
      text: "уведомления",
      userId: "100500"
    });
    assert.equal(status1.handled, true);
    assert.match(status1.response.text, /включены/i);

    const testMessage = await modules.handleNotificationSettingsCommand({
      text: "тест уведомления",
      userId: "100500"
    });
    assert.equal(testMessage.handled, true);
    assert.match(testMessage.response.text, /Через 10 минут/i);

    // 5) Telegram transport: default chat + alias + allowlist
    const telegram = createTelegramTransport({
      env: {
        TELEGRAM_DRY_RUN: "1",
        TELEGRAM_CHAT_ID: "700700",
        TELEGRAM_TARGETS: "owner=700700,team=-100111,alerts=-100222",
        TELEGRAM_ALLOWED_CHAT_IDS: "-100333"
      }
    });

    const defaultDelivery = await telegram.send({ text: "default route" });
    assert.equal(defaultDelivery.status, "dry_run");
    assert.equal(defaultDelivery.chatId, "700700");

    const aliasDelivery = await telegram.send({
      chatAlias: "team",
      text: "group route"
    });
    assert.equal(aliasDelivery.status, "dry_run");
    assert.equal(aliasDelivery.chatId, "-100111");

    await assert.rejects(
      () => telegram.send({ chatAlias: "missing", text: "bad alias" }),
      /Неизвестный Telegram chat alias/i
    );

    await assert.rejects(
      () => telegram.send({ chatId: "-100999", text: "forbidden" }),
      /Telegram chatId не разрешен/i
    );

    // 6) time notifications: t-10 + exact + dedup
    let nowTs = Date.UTC(2026, 1, 27, 9, 2, 0, 0); // 12:02 МСК
    const dueDate = toMoscowDateString(nowTs);
    const todoProvider = createMemoryTodoProvider([
      {
        id: "task-1",
        title: "Подготовить отчёт",
        dueDate,
        dueTime: "12:12",
        project: "Работа",
        label: "Срочно",
        isClosed: false
      }
    ]);

    const modulesWithTasks = createBotModules(env, console, {
      todoProvider,
      now: () => nowTs
    });

    const outbox = [];
    const sendMessage = async (message) => outbox.push(message);

    const tMinusRun = await modulesWithTasks.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(tMinusRun.sent.length, 1);
    assert.equal(tMinusRun.sent[0].triggerType, "tminus10");
    assert.match(outbox[0].text, /Через 10 минут/i);

    nowTs += 60 * 1000;
    const dedupRun = await modulesWithTasks.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(dedupRun.sent.length, 0);

    nowTs = Date.UTC(2026, 1, 27, 9, 12, 0, 0); // 12:12 МСК
    const exactRun = await modulesWithTasks.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(exactRun.sent.length, 1);
    assert.equal(exactRun.sent[0].triggerType, "exact");
    assert.match(outbox[1].text, /Коротко: делай/i);

    const exactDedupRun = await modulesWithTasks.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(exactDedupRun.sent.length, 0);

    // 7) quiet mode blocks time notifications
    await modulesWithTasks.handleNotificationSettingsCommand({
      text: "/quiet on",
      userId: "100500"
    });
    nowTs = Date.UTC(2026, 1, 27, 9, 2, 30, 0);

    const quietRun = await modulesWithTasks.taskTimeNotificationsJob.run({
      userId: "100500",
      chatId: "700700",
      sendMessage
    });
    assert.equal(quietRun.status, "quiet");

    await modulesWithTasks.handleNotificationSettingsCommand({
      text: "/quiet off",
      userId: "100500"
    });

    const notificationLog = JSON.parse(await readFile(notificationLogFile, "utf-8"));
    assert.ok(Array.isArray(notificationLog.entries));
    assert.equal(notificationLog.entries.length, 2);

    console.log("SMOKE OK: сценарии сотрудников и уведомлений пройдены");
  } finally {
    await rm(cacheFile, { force: true });
    await rm(settingsFile, { force: true });
    await rm(notificationLogFile, { force: true });
  }
}

run().catch((error) => {
  console.error("SMOKE FAIL", error);
  process.exit(1);
});
