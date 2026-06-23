import { notFound } from 'next/navigation';
import { listAudits } from '@/lib/audit';
import { canSeeAudit } from '@/lib/audit-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';
import { AuditView } from '@/components/audit/AuditView';

export const dynamic = 'force-dynamic';

export default async function AuditPage() {
  const session = await getSession();
  if (!canSeeAudit(session.email, session.role) && !isPreviewMode()) {
    notFound();
  }
  const audits = await listAudits();
  return <AuditView initialAudits={audits} />;
}
