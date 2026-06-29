import type { ReactNode } from 'react';
import { getAlerts } from '@/lib/alerts';
import { AlertsHeader, type AlertsCounts } from '@/components/alerts/AlertsHeader';

export const dynamic = 'force-dynamic';

export default async function AlertsLayout({ children }: { children: ReactNode }) {
  const data = await getAlerts();
  const burningCritical = data.burning.filter((b) => b.severity === 'critical').length;
  const silentCritical = data.silent.filter((s) => s.severity === 'critical').length;
  const counts: AlertsCounts = {
    dealsCritical: burningCritical + silentCritical,
    burningCritical,
    silentCount: data.silent.length,
    overdueCount: data.tasks.filter((t) => t.overdue).length,
    controlCount: data.tasks.filter((t) => !t.overdue && t.status === 4).length,
  };
  return (
    <div className="bb-page bb-fade">
      <AlertsHeader snapshotDate={data.snapshotDate} counts={counts} />
      {children}
    </div>
  );
}
