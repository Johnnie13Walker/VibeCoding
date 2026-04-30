import { TodoistProvider } from "./providers/todoist-provider.mjs";

export function createProvider(cfg) {
  if (cfg.provider === "todoist" || cfg.provider === "auto") {
    if (!cfg.todoToken) {
      throw new Error("TODO_TOKEN is empty. Set TODO_TOKEN in /etc/openclaw/todo.env");
    }
    return new TodoistProvider({ token: cfg.todoToken });
  }
  throw new Error(`Unsupported TODO_PROVIDER: ${cfg.provider}`);
}
