import { normalizeTasks } from "../models/task.js";
import { compareMoscowDates, getMoscowParts, toMoscowDateString } from "../time/moscowTime.js";

function formatTasksLines(tasks) {
  if (!tasks.length) return "- нет";
  return tasks.map((task) => `- ${task.title}`).join("\n");
}

export function createEveningReminderJob({
  todoProvider,
  now = () => Date.now(),
  logger = console
}) {
  return {
    name: "evening_reminder",
    schedule: "0 19 * * *",
    timezone: "Europe/Moscow",

    async run({ userId, chatId, sendMessage }) {
      const currentTs = now();
      const moscowNow = getMoscowParts(currentTs);
      if (moscowNow.hour !== 19) {
        return { status: "skip_outside_19_msk", sent: false };
      }

      const today = toMoscowDateString(currentTs);
      const rawTasks = await todoProvider.listTasksForTodayAndOverdue({
        userId,
        chatId,
        nowTs: currentTs
      });
      const tasks = normalizeTasks(rawTasks, { nowTs: currentTs }).filter(
        (task) => !task.isClosed && task.dueDate
      );

      const overdue = tasks.filter((task) => compareMoscowDates(task.dueDate, today) < 0);
      const openToday = tasks.filter((task) => task.dueDate === today);

      const lines = [
        "🌙 Вечерний разбор",
        `⚠️ Просрочки (${overdue.length})`,
        formatTasksLines(overdue),
        `✅ Не закрыто на сегодня (${openToday.length})`,
        formatTasksLines(openToday),
        "Давай, блядь, закрывай, не тяни."
      ];

      const text = lines.join("\n");
      await sendMessage({ userId, chatId, text, triggerType: "evening" });

      logger.info?.(`[evening_reminder] sent overdue=${overdue.length} today_open=${openToday.length}`);
      return { status: "ok", sent: true, overdueCount: overdue.length, openTodayCount: openToday.length };
    }
  };
}
