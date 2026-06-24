import { notFound } from 'next/navigation';
import { getAudit, listAssignableUsers } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';
import { AuditReport } from '@/components/audit/AuditReport';

export const dynamic = 'force-dynamic';

export default async function AuditReportPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await getSession();
  if (!canSeeAudit(session.email, session.role) && !isPreviewMode()) {
    notFound();
  }
  const { id } = await params;
  const [audit, managers] = await Promise.all([getAudit(parseInt(id, 10)), listAssignableUsers()]);
  if (!audit) notFound();
  return <AuditReport initialAudit={audit} managers={managers} />;
}
