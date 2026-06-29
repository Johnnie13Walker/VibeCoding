import { getAlerts } from '@/lib/alerts';
import { DealsAlerts } from '@/components/alerts/DealsAlerts';

export const dynamic = 'force-dynamic';

export default async function AlertsDealsPage() {
  const data = await getAlerts();
  return <DealsAlerts data={data} />;
}
