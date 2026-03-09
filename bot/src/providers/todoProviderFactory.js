import { createFixtureTodoProvider } from "./memoryTodoProvider.js";
import { createTodoistTasksProvider } from "./todoistTasksProvider.js";

export function createTodoProvider({ config, logger = console }) {
  if (config.useFixtureTasks) {
    return createFixtureTodoProvider({ config });
  }

  if (config.todoProvider === "todoist" && config.todoToken) {
    return createTodoistTasksProvider({ token: config.todoToken, logger });
  }

  logger.warn?.("[todoProvider] fallback to empty provider (provider/token not configured)");
  return {
    async listTasksForTodayAndOverdue() {
      return [];
    }
  };
}
