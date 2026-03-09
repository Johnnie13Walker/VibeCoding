export function buildSchedulerJobs({ taskTimeNotificationsJob, eveningReminderJob }) {
  return [
    {
      name: taskTimeNotificationsJob.name,
      schedule: taskTimeNotificationsJob.schedule,
      timezone: taskTimeNotificationsJob.timezone,
      run: taskTimeNotificationsJob.run
    },
    {
      name: eveningReminderJob.name,
      schedule: eveningReminderJob.schedule,
      timezone: eveningReminderJob.timezone,
      run: eveningReminderJob.run
    }
  ];
}
