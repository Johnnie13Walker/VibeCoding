import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type { TaskDaySnapshot } from "../schemas/task.schema";

export interface TasksDayQuery {
  dateMsk: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
}

export interface TasksProvider {
  readonly providerId?: string;
  getDaySnapshot(input: TasksDayQuery): Promise<TaskDaySnapshot>;
}

export class NullTasksProvider implements TasksProvider {
  readonly providerId = "null-tasks";

  async getDaySnapshot(input: TasksDayQuery): Promise<TaskDaySnapshot> {
    return {
      dateMsk: input.dateMsk,
      tasksForToday: [],
      overdueTasks: [],
      sourceAvailable: false,
      limitation: "Task provider еще не подключен к личному контуру.",
    };
  }
}
