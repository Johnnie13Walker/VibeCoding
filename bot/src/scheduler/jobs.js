export function buildSchedulerJobs({
  taskTimeNotificationsJob,
  selfHealingJob
}) {
  return [
    {
      name: taskTimeNotificationsJob.name,
      schedule: taskTimeNotificationsJob.schedule,
      timezone: taskTimeNotificationsJob.timezone,
      run: taskTimeNotificationsJob.run
    },
    {
      name: selfHealingJob.name,
      schedule: selfHealingJob.schedule,
      timezone: selfHealingJob.timezone,
      run: selfHealingJob.run
    }
  ];
}
