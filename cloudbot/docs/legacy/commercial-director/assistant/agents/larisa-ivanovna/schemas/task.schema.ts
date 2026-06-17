export type TaskPriority = "low" | "medium" | "high";
export type TaskBucket = "today" | "overdue";
export type TaskStatus = "open" | "in_progress" | "done" | "blocked";

export interface TaskItem {
  id: string;
  title: string;
  bucket: TaskBucket;
  priority?: TaskPriority;
  status?: TaskStatus;
  dueAtMsk?: string;
  notes?: string;
  sourceId?: string;
  source: "todo";
}

export interface TaskDaySnapshot {
  dateMsk: string;
  tasksForToday: TaskItem[];
  overdueTasks: TaskItem[];
  sourceAvailable: boolean;
  limitation?: string;
}
