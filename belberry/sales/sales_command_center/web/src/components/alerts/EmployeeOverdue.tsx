import Link from 'next/link';
import { ExternalLink, ChevronLeft } from 'lucide-react';
import type { OverdueTaskItem, OverdueActivityItem } from '@/lib/bitrix';
import { effLevel, type TeamMemberHealth } from '@/lib/team-health';

const PORTAL = 'https://belberrycrm.bitrix24.ru';
const taskUrl = (managerId: number, id: number) => `${PORTAL}/company/personal/user/${managerId}/tasks/task/view/${id}/`;
const dealUrl = (id: number) => `${PORTAL}/crm/deal/details/${id}/`;

const EFF_COLOR = { good: '#1a7f37', warn: '#b5651d', bad: '#d4202e', unknown: '#9a9aa0' } as const;

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase();
}

function fmtDeadline(iso: string | null): string {
  if (!iso) return 'без срока';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

const ACT_META: Record<string, { icon: string; label: string; bg: string }> = {
  CALL: { icon: '📞', label: 'Звонок', bg: '#eef0fd' },
  MEETING: { icon: '📅', label: 'Встреча', bg: '#fdeef6' },
  EMAIL: { icon: '✉️', label: 'Письмо', bg: '#e6f4ea' },
  TODO: { icon: '📋', label: 'Дело', bg: '#fdf2e7' },
};
function actMeta(provider: string | null) {
  return (provider && ACT_META[provider]) || { icon: '📌', label: 'Активность', bg: '#f4f3f0' };
}

function Stat({ value, label, color }: { value: string; label: string; color?: string }) {
  return (
    <div style={{ textAlign: 'center', background: '#faf8f5', border: '1px solid var(--bb-line)', borderRadius: 12, padding: '8px 16px' }}>
      <div style={{ fontSize: 18, fontWeight: 800, fontVariantNumeric: 'tabular-nums', color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--bb-faint)', textTransform: 'uppercase', letterSpacing: '0.03em', marginTop: 2 }}>{label}</div>
    </div>
  );
}

function GroupTitle({ icon, text, count }: { icon: string; text: string; count: number }) {
  return (
    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--bb-muted)', textTransform: 'uppercase', letterSpacing: '0.03em', margin: '18px 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
      <span>{icon}</span> {text}
      <span style={{ background: '#fdeced', color: 'var(--bb-red)', borderRadius: 999, padding: '1px 8px', fontSize: 11 }}>{count}</span>
    </div>
  );
}

/** Detail-страница: все просрочки сотрудника (задачи Bitrix + CRM-дела), живьём. */
export function EmployeeOverdue({
  managerId,
  member,
  tasks,
  activities,
}: {
  managerId: number;
  member: TeamMemberHealth | null;
  tasks: OverdueTaskItem[];
  activities: OverdueActivityItem[];
}) {
  const name = member?.name ?? `#${managerId}`;
  const eff = member?.efficiencyPct ?? null;
  const lvl = effLevel(eff);

  return (
    <>
      <Link href="/alerts/tasks" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--bb-violet)', fontSize: 13, fontWeight: 600, textDecoration: 'none', marginBottom: 14 }}>
        <ChevronLeft size={16} /> Команда · Алерты
      </Link>

      <div className="bb-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 4 }}>
          <span className="bb-th-av" style={{ width: 52, height: 52, flexBasis: 52, fontSize: 18 }}>{initials(name)}</span>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em' }}>{name}</div>
            <div style={{ fontSize: 13, color: 'var(--bb-faint)' }}>{member?.dept ?? ''}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, marginLeft: 'auto' }}>
            <Stat value={eff == null ? '—' : `${Math.round(eff)}%`} label="Эффективность Б24" color={EFF_COLOR[lvl]} />
            <Stat value={String(tasks.length)} label="Задачи просроч." color={tasks.length ? '#d4202e' : '#2c7a4a'} />
            <Stat value={String(activities.length)} label="Дела просроч." color={activities.length ? '#d4202e' : '#2c7a4a'} />
          </div>
        </div>

        <GroupTitle icon="🗒" text="Задачи" count={tasks.length} />
        {tasks.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)', fontSize: 13, padding: '8px 0' }}>Просроченных задач нет.</p>
        ) : (
          tasks.map((t) => (
            <div key={t.id} className="bb-alert-row">
              <span className="bb-sect-ic" style={{ background: '#fdf2e7' }}>🗒</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <a href={taskUrl(managerId, t.id)} target="_blank" rel="noopener noreferrer" className="bb-alert-title">
                  {t.title} <ExternalLink size={12} />
                </a>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--bb-red)', whiteSpace: 'nowrap' }}>{fmtDeadline(t.deadline)}</div>
            </div>
          ))
        )}

        <GroupTitle icon="📞" text="Дела (CRM)" count={activities.length} />
        {activities.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)', fontSize: 13, padding: '8px 0' }}>Просроченных дел нет.</p>
        ) : (
          activities.map((a) => {
            const meta = actMeta(a.providerTypeId);
            const href = a.ownerTypeId === 2 && a.ownerId ? dealUrl(a.ownerId) : undefined;
            const title = (
              <span className="bb-alert-title">
                {meta.label} — {a.subject || 'без темы'} {href ? <ExternalLink size={12} /> : null}
              </span>
            );
            return (
              <div key={a.id} className="bb-alert-row">
                <span className="bb-sect-ic" style={{ background: meta.bg }}>{meta.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="bb-alert-title">
                      {meta.label} — {a.subject || 'без темы'} <ExternalLink size={12} />
                    </a>
                  ) : (
                    title
                  )}
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--bb-red)', whiteSpace: 'nowrap' }}>{fmtDeadline(a.endTime)}</div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
