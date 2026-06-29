import { getAlerts } from '@/lib/alerts';
import { TasksAlerts } from '@/components/alerts/TasksAlerts';

export const dynamic = 'force-dynamic';

export default async function AlertsTasksPage() {
  const data = await getAlerts();
  return <TasksAlerts data={data} />;
}
