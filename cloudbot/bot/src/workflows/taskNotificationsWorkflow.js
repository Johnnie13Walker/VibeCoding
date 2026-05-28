import { normalizeTasks } from "../models/task.js";

const WINDOW_MS = 5 * 60 * 1000;
const TEN_MINUTES_MS = 10 * 60 * 1000;

function toContext(task) {
  const context = [task.project, task.label].filter(Boolean).join(", ");
  return context ? ` (${context})` : "";
}

function buildMessage(task, triggerType) {
  const context = toContext(task);
  if (triggerType === "tminus10") {
    return `⏰ Через 10 минут: ${task.title}${context}`;
  }
  return `🔥 Сейчас: ${task.title}${context}\nКоротко: делай.`;
}

function inWindow(nowTs, triggerTs) {
  return nowTs >= triggerTs && nowTs < triggerTs + WINDOW_MS;
}

function makeLogKey({ userId, chatId, taskId, triggerType, dueTimestamp }) {
  return `${userId}:${chatId}:${taskId}:${triggerType}:${dueTimestamp}`;
}

export function createTaskTimeNotificationsJob({
  todoProvider,
  settingsStore,
  notificationLogStore,
  now = () => Date.now(),
  logger = console
}) {
  return {
    name: "task_time_notifications",
    schedule: "*/5 * * * *",
    timezone: "Europe/Moscow",

    async run({ userId, chatId, sendMessage }) {
      const currentTs = now();
      const settings = await settingsStore.getUserSettings(userId);
      if (settings.quietMode) {
        return { status: "quiet", sent: [] };
      }

      const rawTasks = await todoProvider.listTasksForTodayAndOverdue({
        userId,
        chatId,
        nowTs: currentTs
      });
      const tasks = normalizeTasks(rawTasks, { nowTs: currentTs }).filter(
        (task) => !task.isClosed && Number.isFinite(task.computedDueDateTime)
      );

      const sent = [];
      for (const task of tasks) {
        const dueTsMs = task.computedDueDateTime * 1000;
        const triggers = [
          { type: "tminus10", triggerTs: dueTsMs - TEN_MINUTES_MS },
          { type: "exact", triggerTs: dueTsMs }
        ];

        for (const trigger of triggers) {
          if (!inWindow(currentTs, trigger.triggerTs)) continue;

          const key = makeLogKey({
            userId,
            chatId,
            taskId: task.id,
            triggerType: trigger.type,
            dueTimestamp: task.computedDueDateTime
          });

          const alreadySent = await notificationLogStore.wasSent(key, currentTs);
          if (alreadySent) continue;

          const text = buildMessage(task, trigger.type);
          await sendMessage({ userId, chatId, text, triggerType: trigger.type, task });
          await notificationLogStore.markSent({
            key,
            sentAt: currentTs,
            payload: {
              userId,
              chatId,
              taskId: task.id,
              triggerType: trigger.type,
              dueTimestamp: task.computedDueDateTime
            }
          });

          sent.push({ taskId: task.id, triggerType: trigger.type, text });
        }
      }

      logger.info?.(`[task_time_notifications] sent=${sent.length}`);
      return { status: "ok", sent };
    }
  };
}
