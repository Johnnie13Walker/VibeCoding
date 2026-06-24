'use client';

import { useMemo, useState } from 'react';
import { Flame, Clock, BellRing, ExternalLink, VolumeX } from 'lucide-react';
import type { AlertManager, AlertsData } from '@/lib/alerts';
import { BURNING_TOP, SILENT_TOP, TASKS_TOP, TASK_KINDS, burnComparator, filterSection, filterTasks, sectionManagers, type BurnSort, type TaskKind } from '@/lib/alerts-filter';
import { ManagerPicker } from '@/components/telemarketing/ManagerPicker';
import { TaskTypePicker } from '@/components/alerts/TaskTypePicker';
import { BurningSortPicker } from '@/components/alerts/BurningSortPicker';

const PORTAL = 'https://belberrycrm.bitrix24.ru';
const dealUrl = (id: number) => `${PORTAL}/crm/deal/details/${id}/`;
const taskUrl = (id: number) => `${PORTAL}/company/personal/user/12/tasks/task/view/${id}/`;

function fmtDeadline(iso: string | null): string {
  if (!iso) return 'без срока';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(iso));
  } catch { return iso; }
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(`${iso}T00:00:00+03:00`));
  } catch { return iso; }
}

/** Полная дата ДД.ММ.ГГГГ — для колонки «последний контакт» в «Горит». */
function fmtDateFull(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Moscow' }).format(new Date(`${iso}T00:00:00+03:00`));
  } catch { return iso; }
}

/** Кал. дней между датой контакта и датой снимка (для «N дн. назад»). */
function daysAgo(from: string, to: string | null): number | null {
  if (!to) return null;
  const f = new Date(`${from}T00:00:00Z`).getTime();
  const t = new Date(`${to}T00:00:00Z`).getTime();
  if (Number.isNaN(f) || Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((t - f) / 86_400_000));
}

function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

/** Пикер менеджеров в заголовке секции (справа, рядом с подписью). Скрыт, если
 * менеджеров нет. `small` в .bb-sect-head уже имеет margin-left:auto и уводит вправо
 * себя и пикер — отдельный auto не нужен. */
function SectionPicker({ managers, selected, onChange }: { managers: AlertManager[]; selected: Set<number>; onChange: (s: Set<number>) => void }) {
  if (managers.length === 0) return null;
  return <ManagerPicker managers={managers} selected={selected} onChange={onChange} allWord="менеджеры" />;
}

export function AlertsView({ data }: { data: AlertsData }) {
  const lookup = useMemo(() => new Map(data.managers.map((m) => [m.managerId, m])), [data.managers]);

  // Свой набор менеджеров и свой выбор (по умолчанию все) — для каждой секции.
  const burningManagers = useMemo(() => sectionManagers(data.burning, lookup), [data.burning, lookup]);
  const silentManagers = useMemo(() => sectionManagers(data.silent, lookup), [data.silent, lookup]);
  const taskManagers = useMemo(() => sectionManagers(data.tasks, lookup), [data.tasks, lookup]);

  const [selB, setSelB] = useState<Set<number>>(() => new Set(burningManagers.map((m) => m.managerId)));
  const [selS, setSelS] = useState<Set<number>>(() => new Set(silentManagers.map((m) => m.managerId)));
  const [selT, setSelT] = useState<Set<number>>(() => new Set(taskManagers.map((m) => m.managerId)));
  const [selKind, setSelKind] = useState<Set<TaskKind>>(() => new Set(TASK_KINDS));
  const [burnSort, setBurnSort] = useState<BurnSort>('nomove');

  const burning = useMemo(
    () => filterSection(data.burning, selB, burningManagers.length, BURNING_TOP, burnComparator(burnSort, data.snapshotDate)),
    [data.burning, selB, burningManagers.length, burnSort, data.snapshotDate],
  );
  const silent = useMemo(() => filterSection(data.silent, selS, silentManagers.length, SILENT_TOP), [data.silent, selS, silentManagers.length]);
  const tasks = useMemo(() => filterTasks(data.tasks, selT, taskManagers.length, selKind, TASKS_TOP), [data.tasks, selT, taskManagers.length, selKind]);

  const criticalCount = burning.filter((b) => b.severity === 'critical').length;
  const overdueCount = tasks.filter((t) => t.overdue).length;

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #6a1f2b, #2b2a5e)' }}>
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Требуют действий · снимок {data.snapshotDate ?? '—'}</div>
            <h1 className="bb-hero-title">Алерты</h1>
            <div className="bb-hero-sub">
              {criticalCount} критичных сделок · {silent.length} молчат &gt;14 дней · {overdueCount} просроченных задач
            </div>
          </div>
          <BellRing size={40} color="#fff" style={{ opacity: 0.9 }} />
        </div>
      </div>

      {/* Горит */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic" style={{ background: '#fdeced', color: '#d4202e' }}><Flame size={17} /></span>
          <h2>Горит</h2>
          <small>застрявшие сделки · топ-{burning.length}</small>
          <div style={{ display: 'flex', gap: 8 }}>
            <BurningSortPicker value={burnSort} onChange={setBurnSort} />
            <SectionPicker managers={burningManagers} selected={selB} onChange={setSelB} />
          </div>
        </div>
        {burning.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Горящих сделок нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {burning.map((d) => (
              <li key={d.dealId} className="bb-alert-row">
                <span className={`bb-sev ${d.severity}`} aria-hidden />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <a href={dealUrl(d.dealId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title">
                    {d.title} <ExternalLink size={12} />
                  </a>
                  <p className="bb-alert-meta">
                    {d.stageLabel} · {d.manager}
                    <span className={`bb-reason ${d.severity}`}>{d.reason}</span>
                  </p>
                </div>
                <div className="bb-comm">
                  <div className="bb-comm-lbl">последний контакт</div>
                  {d.lastCommAt ? (
                    <>
                      <div className="bb-comm-val">{fmtDateFull(d.lastCommAt)}</div>
                      {daysAgo(d.lastCommAt, data.snapshotDate) != null ? (
                        <div className="bb-comm-ago">{daysAgo(d.lastCommAt, data.snapshotDate)} дн. назад</div>
                      ) : null}
                    </>
                  ) : (
                    <div className="bb-comm-none">контакта не было</div>
                  )}
                </div>
                <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                  <p className="tabular" style={{ fontWeight: 700, fontSize: 14 }}>{rub(d.amount)}</p>
                  <p style={{ fontSize: 12, fontWeight: 600, color: d.severity === 'critical' ? '#d4202e' : '#b5651d' }}>
                    {d.stuckDays} дн. без движения
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Тишина — нет коммуникации с клиентом >14 дней */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic" style={{ background: '#eef0fd', color: '#5b50d6' }}><VolumeX size={17} /></span>
          <h2>Тишина</h2>
          <small>нет коммуникации &gt;14 дней · {silent.length}</small>
          <SectionPicker managers={silentManagers} selected={selS} onChange={setSelS} />
        </div>
        {silent.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Сделок без коммуникации больше 14 дней нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {silent.map((d) => (
              <li key={d.dealId} className="bb-alert-row">
                <span className={`bb-sev ${d.severity}`} aria-hidden />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <a href={dealUrl(d.dealId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title">
                    {d.title} <ExternalLink size={12} />
                  </a>
                  <p className="bb-alert-meta">
                    {d.stageLabel} · {d.manager}
                    <span className={`bb-reason ${d.severity}`}>{d.reason}</span>
                  </p>
                </div>
                <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                  <p className="tabular" style={{ fontWeight: 700, fontSize: 14 }}>{rub(d.amount)}</p>
                  <p style={{ fontSize: 12, fontWeight: 600, color: d.severity === 'critical' ? '#d4202e' : '#b5651d' }}>
                    {d.lastCommAt ? `последний контакт ${fmtDate(d.lastCommAt)}` : `${d.silenceDays} дн. без контакта`}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Обещания на контроле */}
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

      {/* Риск процесса — живые сделки с красными флагами (превентив) */}
      <div className="bb-card" style={{ marginTop: 16 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic" style={{ background: '#fdeced', color: '#d4202e' }}>⚠️</span>
          <h2>Риск процесса</h2>
          <small>живые сделки с провалами процесса · {data.processRisk.length}</small>
        </div>
        {data.processRisk.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Живых сделок с процессными рисками нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {data.processRisk.map((r) => (
              <li key={r.dealId} className="bb-alert-row">
                <div style={{ minWidth: 0, flex: 1 }}>
                  <a href={dealUrl(r.dealId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title" style={{ fontWeight: 600 }}>
                    {r.title} <ExternalLink size={12} />
                  </a>
                  <p className="bb-alert-meta">{r.stageLabel} · {r.manager}</p>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                    {r.flags.map((f, i) => (
                      <span key={i} style={{ fontSize: 11, fontWeight: 600, background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)', borderRadius: 6, padding: '2px 7px' }}>{f}</span>
                    ))}
                  </div>
                </div>
                <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                  <span className={`bb-reason ${r.severity === 'critical' ? 'critical' : ''}`}>{r.severity === 'critical' ? 'критично' : 'риск'}</span>
                  <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 4 }}>
                    <a href="/audit" style={{ color: 'var(--bb-violet)' }}>разобрать →</a>
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
