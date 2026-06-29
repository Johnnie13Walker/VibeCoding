import { notFound } from 'next/navigation';
import { getTeamHealth, findMember, canViewMember } from '@/lib/team-health';
import { getSession } from '@/lib/session';
import { getOverdueTasks, getOverdueActivities } from '@/lib/bitrix';
import { EmployeeOverdue } from '@/components/alerts/EmployeeOverdue';

export const dynamic = 'force-dynamic';

export default async function EmployeeOverduePage({ params }: { params: Promise<{ managerId: string }> }) {
  const { managerId } = await params;
  const id = Number(managerId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  const [health, session] = await Promise.all([getTeamHealth(), getSession()]);
  const member = findMember(health, id);

  // Данные РОПа открыты только директору/владельцу и самому РОПу.
  if (member && !canViewMember({ bitrixId: session.bitrixId, role: session.role }, member)) {
    notFound();
  }

  const [tasks, activities] = await Promise.all([getOverdueTasks(id), getOverdueActivities(id)]);
  return <EmployeeOverdue managerId={id} member={member} tasks={tasks} activities={activities} />;
}
