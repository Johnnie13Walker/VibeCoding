import { getAlerts } from '@/lib/alerts';
import { getTeamHealth } from '@/lib/team-health';
import { TasksAlerts } from '@/components/alerts/TasksAlerts';
import { TeamHealth } from '@/components/alerts/TeamHealth';

export const dynamic = 'force-dynamic';

export default async function AlertsTasksPage() {
  const [alerts, health] = await Promise.all([getAlerts(), getTeamHealth()]);
  return (
    <>
      <TeamHealth data={health} />
      <TasksAlerts data={alerts} />
    </>
  );
}
