/**
 * @typedef {Object} NormalizedTask
 * @property {string} id
 * @property {string} content
 * @property {string|null} dueDateTime
 * @property {string|null} dueDate
 * @property {string|null} url
 * @property {string|null} projectName
 * @property {boolean} completed
 * @property {number} [priority]
 */

/**
 * @typedef {Object} ToDoProvider
 * @property {(dateISO: string) => Promise<NormalizedTask[]>} getTasksForDate
 * @property {(dateISO: string) => Promise<NormalizedTask[]>} getOverdueAndToday
 * @property {(task: NormalizedTask) => boolean} isTaskCompleted
 * @property {(task: any) => NormalizedTask} normalizeTask
 * @property {(payload: {content:string, dueDate?:string|null, dueDateTime?:string|null, dueString?:string|null, priority?:number}) => Promise<NormalizedTask>} createTask
 */
export {};
