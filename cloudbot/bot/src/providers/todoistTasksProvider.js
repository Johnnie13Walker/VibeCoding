import { toMoscowDateString, toMoscowTimeString } from "../time/moscowTime.js";

function normalizeTodoistTask(task) {
  const due = task?.due || {};
  const dueDateTime = typeof due?.datetime === "string" ? due.datetime : null;
  const dueDate = typeof due?.date === "string" ? due.date : null;

  let normalizedDueDate = dueDate || null;
  let normalizedDueTime = null;

  if (dueDateTime) {
    const dueMs = Date.parse(dueDateTime);
    if (Number.isFinite(dueMs)) {
      normalizedDueDate = toMoscowDateString(dueMs);
      normalizedDueTime = toMoscowTimeString(dueMs);
    }
  }

  return {
    id: String(task?.id ?? ""),
    title: task?.content || "(без названия)",
    dueDate: normalizedDueDate,
    dueTime: normalizedDueTime,
    project: null,
    label: null,
    isClosed: Boolean(task?.checked || task?.completed_at)
  };
}

export function createTodoistTasksProvider({ token, fetchImpl = fetch, logger = console }) {
  const baseUrl = "https://api.todoist.com/api/v1";

  async function request(pathWithQuery) {
    const response = await fetchImpl(`${baseUrl}${pathWithQuery}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json"
      }
    });

    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`Todoist API error ${response.status}: ${body.slice(0, 240)}`);
    }

    return response.json();
  }

  async function getAllOpenTasks(limit = 200) {
    const all = [];
    let cursor = null;

    while (all.length < limit) {
      const query = new URLSearchParams({ limit: "100" });
      if (cursor) query.set("cursor", cursor);

      const payload = await request(`/tasks?${query.toString()}`);
      const items = Array.isArray(payload?.results) ? payload.results : [];
      all.push(...items);

      cursor = payload?.next_cursor || null;
      if (!cursor || items.length === 0) break;
    }

    return all.slice(0, limit);
  }

  return {
    async listTasksForTodayAndOverdue({ nowTs = Date.now() } = {}) {
      const today = toMoscowDateString(nowTs);
      const tasks = await getAllOpenTasks();
      const normalized = tasks.map(normalizeTodoistTask);
      return normalized.filter(
        (task) => task.dueDate && task.dueDate <= today && !task.isClosed
      );
    },

    async healthcheck() {
      try {
        const tasks = await getAllOpenTasks(1);
        return { status: "ok", count: tasks.length };
      } catch (error) {
        logger.error?.("[todoistTasksProvider] healthcheck failed", error);
        return { status: "error", error: String(error?.message || error) };
      }
    }
  };
}
