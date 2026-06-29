import { getAlerts } from '@/lib/alerts';
import { getTeamHealth } from '@/lib/team-health';
import { getSession } from '@/lib/session';
import { TasksAlerts } from '@/components/alerts/TasksAlerts';
import { TeamHealth } from '@/components/alerts/TeamHealth';

export const dynamic = 'force-dynamic';

export default async function AlertsTasksPage() {
  const [alerts, health, session] = await Promise.all([getAlerts(), getTeamHealth(), getSession()]);
  return (
    <>
      <TeamHealth data={health} viewer={{ bitrixId: session.bitrixId, role: session.role }} />
      <TasksAlerts data={alerts} />
    </>
  );
}
