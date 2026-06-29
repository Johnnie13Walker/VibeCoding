import Link from 'next/link';
import { effLevel, type TeamHealthData, type TeamMemberHealth } from '@/lib/team-health';

const EFF_COLOR = { good: '#1a7f37', warn: '#b5651d', bad: '#d4202e', unknown: '#9a9aa0' } as const;
const BAR_COLOR = { good: '#2c9a52', warn: '#e88a3b', bad: '#d4202e', unknown: '#cfcfcf' } as const;

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase();
}

function odColor(n: number): string {
  return n > 0 ? '#d4202e' : '#2c7a4a';
}

function Row({ m }: { m: TeamMemberHealth }) {
  const lvl = effLevel(m.efficiencyPct);
  return (
    <Link href={`/alerts/tasks/${m.managerId}`} className="bb-th-row">
      <span className="bb-th-av">{initials(m.name)}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 14.5 }}>{m.name}</div>
        <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>{m.dept ?? ''}</div>
      </div>
      <div style={{ width: 200 }}>
        {m.efficiencyPct == null ? (
          <span style={{ color: 'var(--bb-faint)', fontSize: 13 }}>— нет данных</span>
        ) : (
          <>
            <span className="bb-th-bar">
              <i style={{ width: `${Math.min(100, m.efficiencyPct)}%`, background: BAR_COLOR[lvl] }} />
            </span>
            <b style={{ color: EFF_COLOR[lvl], fontVariantNumeric: 'tabular-nums' }}>{Math.round(m.efficiencyPct)}%</b>
          </>
        )}
      </div>
      <div style={{ width: 70, textAlign: 'center', fontWeight: 700, color: odColor(m.overdueTasks), fontVariantNumeric: 'tabular-nums' }}>{m.overdueTasks}</div>
      <div style={{ width: 70, textAlign: 'center', fontWeight: 700, color: odColor(m.overdueActivities), fontVariantNumeric: 'tabular-nums' }}>{m.overdueActivities}</div>
      <div style={{ width: 70, textAlign: 'center', fontWeight: 800, color: odColor(m.overdueTotal), fontVariantNumeric: 'tabular-nums' }}>{m.overdueTotal}</div>
    </Link>
  );
}

function GroupLabel({ text }: { text: string }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--bb-faint)', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '14px 0 2px', display: 'flex', alignItems: 'center', gap: 7 }}>
      <span style={{ width: 6, height: 6, borderRadius: 999, background: '#5b50d6' }} />
      {text}
    </div>
  );
}

/** Сводный блок над списком задач: эффективность Б24 (наш КПД) + просрочки по
 * отделу продаж и телемаркетингу (две группы). Строка кликабельна →
 * /alerts/tasks/[managerId]. Нет снимка → блок скрыт. */
export function TeamHealth({ data }: { data: TeamHealthData }) {
  if (data.members.length === 0) return null;
  const sales = data.members.filter((m) => m.group === 'sales');
  const tm = data.members.filter((m) => m.group === 'tm');
  return (
    <div className="bb-card" style={{ marginBottom: 16 }}>
      <div className="bb-sect-head">
        <span className="bb-sect-ic" style={{ background: '#eef0fd', color: '#5b50d6' }}>📊</span>
        <h2>Команда · эффективность и просрочки</h2>
        <small>сначала проблемные · Б24 · снимок {data.snapshotDate ?? '—'}</small>
      </div>
      <div className="bb-th-head">
        <span style={{ width: 34 }} />
        <span style={{ flex: 1 }}>Сотрудник</span>
        <span style={{ width: 200 }}>Эффективность Б24</span>
        <span style={{ width: 70, textAlign: 'center' }}>Задачи</span>
        <span style={{ width: 70, textAlign: 'center' }}>Дела</span>
        <span style={{ width: 70, textAlign: 'center' }}>Всего</span>
      </div>
      {sales.length > 0 && (tm.length > 0 ? <GroupLabel text="Отдел продаж" /> : null)}
      {sales.map((m) => <Row key={m.managerId} m={m} />)}
      {tm.length > 0 && <GroupLabel text="Телемаркетинг" />}
      {tm.map((m) => <Row key={m.managerId} m={m} />)}
    </div>
  );
}
