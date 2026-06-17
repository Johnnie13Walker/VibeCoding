import { getAlerts } from '@/lib/alerts';
import { AlertsView } from '@/components/alerts/AlertsView';

export const dynamic = 'force-dynamic';

export default async function AlertsPage() {
  const data = await getAlerts();
  return <AlertsView data={data} />;
}
