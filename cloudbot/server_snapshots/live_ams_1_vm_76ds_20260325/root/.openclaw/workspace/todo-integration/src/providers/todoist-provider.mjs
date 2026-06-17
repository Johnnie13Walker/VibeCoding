function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** @implements {import('./types.mjs').ToDoProvider} */
export class TodoistProvider {
  constructor({ token, fetchImpl = fetch, logger = console, maxAttempts = 3 }) {
    this.token = token;
    this.fetchImpl = fetchImpl;
    this.logger = logger;
    this.baseUrl = "https://api.todoist.com/api/v1";
    this.maxAttempts = Math.max(1, Number(maxAttempts || 3));
  }

  isRetryableStatus(status) {
    const n = Number(status);
    return n >= 500 && n <= 599;
  }

  backoffMs(attempt) {
    const base = 500 * (2 ** Math.max(0, attempt - 1));
    const jitter = Math.floor(Math.random() * 250);
    return base + jitter;
  }

  async requestWithRetry({ path, method = "GET", body = null }) {
    let lastError = null;

    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        const res = await this.fetchImpl(path, {
          method,
          headers: {
            Authorization: `Bearer ${this.token}`,
            Accept: "application/json",
            ...(body ? { "Content-Type": "application/json" } : {})
          },
          ...(body ? { body: JSON.stringify(body) } : {})
        });

        const text = await res.text();
        if (res.ok) {
          if (!text) return {};
          try {
            return JSON.parse(text);
          } catch {
            return {};
          }
        }

        const error = new Error(`Todoist API error ${res.status}: ${text.slice(0, 240)}`);
        lastError = error;

        if (this.isRetryableStatus(res.status) && attempt < this.maxAttempts) {
          const waitMs = this.backoffMs(attempt);
          this.logger.warn?.(`[todoist] retry attempt=${attempt + 1}/${this.maxAttempts} wait_ms=${waitMs} status=${res.status}`);
          await sleep(waitMs);
          continue;
        }

        throw error;
      } catch (err) {
        lastError = err;
        if (attempt < this.maxAttempts) {
          const waitMs = this.backoffMs(attempt);
          this.logger.warn?.(`[todoist] retry attempt=${attempt + 1}/${this.maxAttempts} wait_ms=${waitMs} error=${err?.message || err}`);
          await sleep(waitMs);
          continue;
        }
        throw err;
      }
    }

    throw lastError || new Error("Todoist request failed");
  }

  async request(pathWithQuery) {
    return this.requestWithRetry({
      path: `${this.baseUrl}${pathWithQuery}`,
      method: "GET"
    });
  }

  async requestPost(path, body) {
    return this.requestWithRetry({
      path: `${this.baseUrl}${path}`,
      method: "POST",
      body
    });
  }

  normalizeTask(task) {
    const due = task?.due || {};
    return {
      id: String(task?.id ?? ""),
      content: task?.content || "(без названия)",
      dueDateTime: due?.datetime || null,
      dueDate: due?.date || null,
      url: task?.url || null,
      projectName: null,
      completed: !!task?.checked || !!task?.completed_at,
      priority: Number(task?.priority || 2)
    };
  }

  isTaskCompleted(task) {
    return !!task?.completed;
  }

  async getAllOpenTasks(limit = 200) {
    const all = [];
    let cursor = null;

    while (all.length < limit) {
      const qs = new URLSearchParams({ limit: "100" });
      if (cursor) qs.set("cursor", cursor);
      const payload = await this.request(`/tasks?${qs.toString()}`);
      const items = (payload?.results || []).map((x) => this.normalizeTask(x));
      all.push(...items);
      cursor = payload?.next_cursor || null;
      if (!cursor || !items.length) break;
    }

    return all.slice(0, limit);
  }

  async getTasksForDate(dateISO) {
    const all = await this.getAllOpenTasks();
    return all.filter((t) => t.dueDate === dateISO && !this.isTaskCompleted(t));
  }

  async getOverdueAndToday(dateISO) {
    const all = await this.getAllOpenTasks();
    return all.filter((t) => t.dueDate && t.dueDate <= dateISO && !this.isTaskCompleted(t));
  }

  async createTask({ content, dueDate = null, dueDateTime = null, dueString = null, priority = 2 }) {
    const payload = { content, priority };
    if (dueDateTime) payload.due_datetime = dueDateTime;
    else if (dueDate) payload.due_date = dueDate;
    else if (dueString) payload.due_string = dueString;

    const created = await this.requestPost("/tasks", payload);
    return this.normalizeTask(created);
  }

  async updateTaskDue(taskId, { dueDate = null, dueDateTime = null }) {
    const payload = {};
    if (dueDateTime) payload.due_datetime = dueDateTime;
    else if (dueDate) payload.due_date = dueDate;
    const updated = await this.requestPost(`/tasks/${encodeURIComponent(String(taskId))}`, payload);
    return this.normalizeTask(updated);
  }
}
