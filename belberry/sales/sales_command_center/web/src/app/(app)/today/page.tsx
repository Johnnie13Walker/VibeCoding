import { PhoneCall, PhoneForwarded, Timer, Handshake, FileText, Zap, Activity, CalendarClock, ExternalLink, Mail, MessageCircle } from 'lucide-react';
import { getLive, getDayBreakdown, type LiveData } from '@/lib/live';
import { availableReportDates } from '@/lib/reports';
import { DaySelect } from '@/components/DaySelect';

export const dynamic = 'force-dynamic';

const PORTAL = 'https://belberrycrm.bitrix24.ru';
const dealUrl = (id: number) => `${PORTAL}/crm/deal/details/${id}/`;
const spUrl = (type: number, id: number) => `${PORTAL}/crm/type/${type}/details/${id}/`;

function fmtMsk(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(iso));
  } catch { return iso; }
}
function fmtDay(d: string): string {
  const [y, m, dd] = d.split('-');
  return y && m && dd ? `${dd}.${m}.${y}` : d;
}
function timeOnly(at: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(at));
  } catch { return ''; }
}

const FEED_ICON: Record<string, React.ReactNode> = {
  meeting: <Handshake size={16} />, brief: <FileText size={16} />, kp: <FileText size={16} />, deal: <Zap size={16} />,
};
const FEED_LABEL: Record<string, string> = { meeting: 'встреча', brief: 'бриф', kp: 'КП', deal: 'сделка' };

function Tile({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="bb-card" style={{ padding: 18 }}>
      <div style={{ fontSize: 12, color: 'var(--bb-muted)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: 'var(--bb-violet)', display: 'inline-flex' }}>{icon}</span>{label}
      </div>
      <div className="tabular" style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.03em', marginTop: 8 }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

export default async function TodayPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const params = await searchParams;
  const dates = await availableReportDates();
  const todayMsk = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date());
  // принимаем любую корректную дату (ввод вручную), кроме сегодня (сегодня = live)
  const raw = typeof params.date === 'string' ? params.date : '';
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw));
  const selected = validDate && raw !== todayMsk ? raw : null;
  const isArchive = selected !== null;

  const data: LiveData | null = isArchive ? await getDayBreakdown(selected) : await getLive();
  const empty = !data || (!isArchive && data.updatedAt === null);

  const t = data?.totals;
  const connect = t && t.dials ? Math.round((t.answered / t.dials) * 100) : 0;
  const MSTATUS: Record<string, { label: string; bg: string; color: string }> = {
    held: { label: 'проведена', bg: '#e7f4ec', color: 'var(--bb-green)' },
    scheduled: { label: 'назначена', bg: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' },
    cancelled: { label: 'отменена', bg: '#fdeced', color: 'var(--bb-red)' },
  };

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #3a3780, #5b50d6)' }}>
        <div className="bb-hero-row" style={{ alignItems: 'flex-start', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">{isArchive ? 'Отдел продаж · день из архива' : 'Отдел продаж · реальное время'}</div>
            <h1 className="bb-hero-title">
              {isArchive ? `День ${fmtDay(selected)}` : <><span className="bb-live-dot" style={{ marginRight: 10 }} />Сегодня</>}
            </h1>
            <div className="bb-hero-sub">
              {isArchive
                ? 'сохранённый разбор за выбранный день (чаты и лента — только в режиме «Сегодня»)'
                : (data?.updatedAt ? `обновлено ${fmtMsk(data.updatedAt)} МСК · каждые ~20 мин в рабочие часы` : 'данные ещё не собраны')}
            </div>
          </div>
          <div style={{ flex: '0 0 auto', paddingTop: 4 }}>
            <DaySelect dates={dates} selected={selected} maxDate={todayMsk} />
          </div>
        </div>
      </div>

      {empty || !t ? (
        <div className="bb-card">
          <p style={{ color: 'var(--bb-muted)' }}>
            {isArchive ? 'За этот день нет сохранённых данных.' : 'Снимок текущего дня ещё не сформирован. Появится после ближайшего сбора.'}
          </p>
        </div>
      ) : (
        <>
          <div className="bb-grid bb-grid-4" style={{ marginBottom: 16 }}>
            <Tile icon={<PhoneCall size={14} />} label="Наборы" value={t.dials} />
            <Tile icon={<PhoneForwarded size={14} />} label="Снял трубку" value={t.answered} sub={`${connect}% от наборов`} />
            <Tile icon={<Timer size={14} />} label="Дозвоны ≥60с" value={t.calls60} sub={t.dials ? `${Math.round((t.calls60 / t.dials) * 100)}% от наборов` : undefined} />
            <Tile icon={<MessageCircle size={14} />} label="Чаты Wazzup" value={data!.chatsTracked ? t.chats : '—'} sub={!data!.chatsTracked ? (isArchive ? 'за этот день не собирались' : 'ждёт сбора') : (isArchive ? undefined : (data!.chatsUpdatedAt ? `обновлено ${fmtMsk(data!.chatsUpdatedAt)}` : 'ждёт сбора'))} />
            <Tile icon={<Handshake size={14} />} label="Встречи проведено" value={t.meetingsHeld} sub={`назначено ${t.meetingsScheduled} · отменено ${t.meetingsCancelled}`} />
            <Tile icon={<FileText size={14} />} label="Брифы" value={t.briefs} />
            <Tile icon={<FileText size={14} />} label="КП" value={t.kp} />
            <Tile icon={<Mail size={14} />} label="Письма" value={t.emails} />
            <Tile icon={<Zap size={14} />} label="Сделок создано" value={t.deals} sub={t.dealsSpam ? `${t.dealsSpam} спам исключён` : undefined} />
          </div>

          <div className="bb-card" style={{ marginBottom: 16 }}>
            <div className="bb-sect-head"><span className="bb-sect-ic"><Activity size={17} /></span><h2>По менеджерам</h2><small>{data!.managers.length}</small></div>
            {data!.managers.length === 0 ? (
              <p style={{ color: 'var(--bb-muted)' }}>Активности нет.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="bb-table">
                  <thead><tr><th>Менеджер</th><th className="r">Наборы</th><th className="r" title="снял трубку, любая длительность">Снял</th><th className="r" title="дозвон = разговор ≥60с">Дозв ≥60с</th><th className="r">Чаты</th><th className="r">Письма</th><th className="r" title="проведено · назначено · отменено">Встречи<br /><span style={{ fontWeight: 400, fontSize: 9 }}>пр·наз·отм</span></th><th className="r">Брифы</th><th className="r">КП</th></tr></thead>
                  <tbody>
                    {data!.managers.map((m) => (
                      <tr key={m.managerId}>
                        <td style={{ fontWeight: 600 }}>{m.name}</td>
                        <td className="r">{m.dials}</td><td className="r">{m.answered}</td><td className="r">{m.calls60}</td>
                        <td className="r">{data!.chatsTracked ? m.chats : '—'}</td><td className="r">{m.emails}</td>
                        <td className="r tabular"><b style={{ color: 'var(--bb-green)' }}>{m.mHeld}</b>·{m.mScheduled}·<span style={{ color: m.mCancelled ? 'var(--bb-red)' : 'inherit' }}>{m.mCancelled}</span></td>
                        <td className="r">{m.briefs}</td><td className="r">{m.kp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="bb-grid k2" style={{ gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div className="bb-card">
              <div className="bb-sect-head"><span className="bb-sect-ic"><CalendarClock size={17} /></span><h2>Встречи</h2><small>{t.meetingsHeld} провед. · {t.meetingsScheduled} назнач.{isArchive ? '' : ' сегодня'} · {t.meetingsCancelled} отмен.</small></div>
              {data!.meetings.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>Встреч нет.</p>
              ) : (
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
                  {data!.meetings.map((m, i) => (
                    <li key={i} className="bb-alert-row" style={{ gap: 10 }}>
                      <span className="tabular" style={{ fontWeight: 700, fontSize: 13, color: 'var(--bb-violet)', flex: '0 0 auto' }}>{fmtMsk(m.at)}</span>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        {m.dealId ? <a className="bb-alert-title" href={dealUrl(m.dealId)} target="_blank" rel="noopener noreferrer">{m.title} <ExternalLink size={12} /></a> : <span style={{ fontWeight: 600, fontSize: 14 }}>{m.title}</span>}
                        <p className="bb-alert-meta">{m.manager}</p>
                      </div>
                      <span className="bb-reason" style={{ background: MSTATUS[m.status].bg, color: MSTATUS[m.status].color }}>{MSTATUS[m.status].label}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="bb-card">
              <div className="bb-sect-head"><span className="bb-sect-ic"><FileText size={17} /></span><h2>Брифы</h2><small>{data!.briefs.length}</small></div>
              {data!.briefs.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>Брифов нет.</p>
              ) : (
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
                  {data!.briefs.map((b, i) => (
                    <li key={i} className="bb-alert-row" style={{ gap: 10 }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        {b.id ? <a className="bb-alert-title" href={spUrl(1056, b.id)} target="_blank" rel="noopener noreferrer">{b.title} <ExternalLink size={12} /></a> : <span style={{ fontWeight: 600, fontSize: 14 }}>{b.title}</span>}
                        <p className="bb-alert-meta">
                          {b.manager}
                          {b.dealId ? <> · <a href={dealUrl(b.dealId)} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--bb-violet)' }}>сделка</a></> : null}
                        </p>
                      </div>
                      {b.service ? <span className="bb-reason" style={{ background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>{b.service}</span> : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {!isArchive && (
            <div className="bb-card" style={{ marginTop: 16 }}>
              <div className="bb-sect-head"><span className="bb-sect-ic"><Activity size={17} /></span><h2>Лента</h2><small>события дня</small></div>
              {data!.feed.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>Событий пока нет.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {data!.feed.map((e, i) => (
                    <div key={i} style={{ display: 'flex', gap: 9, alignItems: 'center', fontSize: 13, padding: '8px 10px', border: '1px solid var(--bb-line)', borderRadius: 10 }}>
                      <span style={{ color: 'var(--bb-violet)', display: 'inline-flex' }}>{FEED_ICON[e.kind]}</span>
                      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <b style={{ fontWeight: 600 }}>{e.title}</b> <span style={{ color: 'var(--bb-faint)' }}>· {e.manager} · {FEED_LABEL[e.kind]}</span>
                      </span>
                      <span style={{ marginLeft: 'auto', color: 'var(--bb-faint)', fontSize: 12, whiteSpace: 'nowrap' }}>{timeOnly(e.at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
