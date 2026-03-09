import { readJsonFile } from "../storage/jsonFileStore.js";

export function createMemoryTodoProvider(initialTasks = []) {
  let tasks = Array.isArray(initialTasks) ? [...initialTasks] : [];

  return {
    setTasks(nextTasks) {
      tasks = Array.isArray(nextTasks) ? [...nextTasks] : [];
    },

    async listTasksForTodayAndOverdue() {
      return tasks;
    }
  };
}

export function createFixtureTodoProvider({ config }) {
  return {
    async listTasksForTodayAndOverdue() {
      if (!config.useFixtureTasks) return [];
      const payload = await readJsonFile(config.fixtureTasksFile, { tasks: [] });
      if (Array.isArray(payload)) return payload;
      return Array.isArray(payload?.tasks) ? payload.tasks : [];
    }
  };
}
