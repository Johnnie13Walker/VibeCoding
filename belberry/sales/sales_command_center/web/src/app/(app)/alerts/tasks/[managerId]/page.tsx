import { notFound } from 'next/navigation';
import { getTeamHealth, findMember } from '@/lib/team-health';
import { getOverdueTasks, getOverdueActivities } from '@/lib/bitrix';
import { EmployeeOverdue } from '@/components/alerts/EmployeeOverdue';

export const dynamic = 'force-dynamic';

export default async function EmployeeOverduePage({ params }: { params: Promise<{ managerId: string }> }) {
  const { managerId } = await params;
  const id = Number(managerId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  const [health, tasks, activities] = await Promise.all([
    getTeamHealth(),
    getOverdueTasks(id),
    getOverdueActivities(id),
  ]);

  return <EmployeeOverdue managerId={id} member={findMember(health, id)} tasks={tasks} activities={activities} />;
}
