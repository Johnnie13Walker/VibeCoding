import { Flame, Clock, BellRing, ExternalLink } from 'lucide-react';
import { getAlerts } from '@/lib/alerts';

export const dynamic = 'force-dynamic';

const PORTAL = 'https://belberrycrm.bitrix24.ru';
const dealUrl = (id: number) => `${PORTAL}/crm/deal/details/${id}/`;
const taskUrl = (id: number) => `${PORTAL}/company/personal/user/12/tasks/task/view/${id}/`;

function fmtDeadline(iso: string | null): string {
  if (!iso) return 'без срока';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(iso));
  } catch { return iso; }
}

function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

export default async function AlertsPage() {
  const data = await getAlerts();
  const criticalCount = data.burning.filter((b) => b.severity === 'critical').length;
  const overdueCount = data.tasks.filter((t) => t.overdue).length;

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #6a1f2b, #2b2a5e)' }}>
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Требуют действий · снимок {data.snapshotDate ?? '—'}</div>
            <h1 className="bb-hero-title">Алерты</h1>
            <div className="bb-hero-sub">
              {criticalCount} критичных сделок · {overdueCount} просроченных задач
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
          <small>застрявшие сделки · топ-{data.burning.length}</small>
        </div>
        {data.burning.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Горящих сделок нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {data.burning.map((d) => (
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
                    {d.stuckDays} дн. без движения
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
          <small>из разбора встреч · {data.tasks.length}</small>
        </div>
        {data.tasks.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Открытых задач из разборов нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {data.tasks.map((t) => (
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
    </div>
  );
}
