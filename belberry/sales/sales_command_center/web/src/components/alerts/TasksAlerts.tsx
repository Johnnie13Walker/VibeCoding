'use client';

import { useMemo, useState } from 'react';
import { Clock, ExternalLink } from 'lucide-react';
import type { AlertsData } from '@/lib/alerts';
import { TASKS_TOP, TASK_KINDS, filterTasks, sectionManagers, type TaskKind } from '@/lib/alerts-filter';
import { TaskTypePicker } from '@/components/alerts/TaskTypePicker';
import { SectionPicker, dealUrl, taskUrl, fmtDeadline } from '@/components/alerts/shared';

/** Вкладка «Задачи» (/alerts/tasks) — просрочки и задачи на контроле из разбора встреч. */
export function TasksAlerts({ data }: { data: AlertsData }) {
  const lookup = useMemo(() => new Map(data.managers.map((m) => [m.managerId, m])), [data.managers]);
  const taskManagers = useMemo(() => sectionManagers(data.tasks, lookup), [data.tasks, lookup]);

  const [selT, setSelT] = useState<Set<number>>(() => new Set(taskManagers.map((m) => m.managerId)));
  const [selKind, setSelKind] = useState<Set<TaskKind>>(() => new Set(TASK_KINDS));

  const tasks = useMemo(() => filterTasks(data.tasks, selT, taskManagers.length, selKind, TASKS_TOP), [data.tasks, selT, taskManagers.length, selKind]);

  return (
    <div className="bb-card">
      <div className="bb-sect-head">
        <span className="bb-sect-ic" style={{ background: '#fdf2e7', color: '#b5651d' }}><Clock size={17} /></span>
        <h2>Задачи на контроле</h2>
        <small>из разбора встреч · {tasks.length}</small>
        <div style={{ display: 'flex', gap: 8 }}>
          <TaskTypePicker selected={selKind} onChange={setSelKind} />
          <SectionPicker managers={taskManagers} selected={selT} onChange={setSelT} />
        </div>
      </div>
      {tasks.length === 0 ? (
        <p style={{ color: 'var(--bb-muted)' }}>Открытых задач из разборов нет.</p>
      ) : (
        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
          {tasks.map((t) => (
            <li key={t.taskId} className="bb-alert-row">
              <div style={{ minWidth: 0, flex: 1 }}>
                <a href={taskUrl(t.taskId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title" style={{ fontWeight: 600 }}>
                  {t.title} <ExternalLink size={12} />
                </a>
                <p className="bb-alert-meta">
                  {t.manager}
                  {t.dealId ? <> · <a href={dealUrl(t.dealId)} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--bb-violet)' }}>сделка</a></> : null}
                </p>
              </div>
              <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                {t.overdue ? (
                  <span className="bb-reason critical">просрочена</span>
                ) : t.status === 4 ? (
                  <span className="bb-reason" style={{ background: '#e6f4ea', color: '#1a7f37' }}>на контроле</span>
                ) : (
                  <span className="bb-reason" style={{ background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>{t.statusLabel}</span>
                )}
                <p style={{ fontSize: 12, color: t.overdue ? '#d4202e' : 'var(--bb-faint)', marginTop: 4 }}>дедлайн: {fmtDeadline(t.deadline)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
