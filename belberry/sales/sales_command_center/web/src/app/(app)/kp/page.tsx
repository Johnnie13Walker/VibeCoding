import { listKpJobs } from '@/lib/kp';
import { KpView } from '@/components/kp/KpView';

export const dynamic = 'force-dynamic';

export default async function KpPage() {
  const jobs = await listKpJobs();
  return <KpView initialJobs={jobs} />;
}
