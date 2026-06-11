import { notFound } from 'next/navigation';
import { listKpJobs } from '@/lib/kp';
import { canSeeKp } from '@/lib/kp-access';
import { isPreviewMode } from '@/lib/preview';
import { getSession } from '@/lib/session';
import { KpView } from '@/components/kp/KpView';

export const dynamic = 'force-dynamic';

export default async function KpPage() {
  const session = await getSession();
  // пилот: страница существует только для перечисленных пользователей
  if (!canSeeKp(session.email) && !isPreviewMode()) {
    notFound();
  }
  const jobs = await listKpJobs();
  return <KpView initialJobs={jobs} />;
}
