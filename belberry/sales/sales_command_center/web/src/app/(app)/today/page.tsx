import { PhoneCall, PhoneForwarded, Timer, Handshake, FileText, Zap, Activity, CalendarClock, ExternalLink, Mail, MessageCircle } from 'lucide-react';
import { getLive, getDayBreakdown, type LiveData, type LiveMeeting } from '@/lib/live';
import { DaySelect } from '@/components/DaySelect';
import { FeedView } from '@/components/today/FeedView';

// Данные Командного центра ведутся с запуска (1 июня 2026) — раньше выбирать нечего.
const DATA_START = '2026-06-01';

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

const spUrlKp = (id: number) => spUrl(1106, id);

// Порог годовой выручки для телемаркетинга: ниже — кандидат на автоотвал (подсветка).
const REVENUE_LOW_THRESHOLD = 30_000_000;

const MEETING_TYPE: Record<string, { label: string; color: string; bg: string }> = {
  briefing: { label: 'Брифинг', color: '#4a3fd0', bg: '#eef0ff' },
  defense: { label: 'Защита КП', color: '#c0297e', bg: '#fdeef6' },
};
const STATUS_PILL: Record<string, { label: string; bg: string; color: string }> = {
  held: { label: 'проведена', bg: '#e7f4ec', color: 'var(--bb-green)' },
  scheduled: { label: 'назначена', bg: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' },
  cancelled: { label: 'отменена', bg: '#fdeced', color: 'var(--bb-red)' },
};
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

// Срезаем хвост «(Брифинг)»/«(Бриффинг)»/«(Защита КП)» из названия встречи —
// тип уже показан плашкой, дублировать в заголовке (да ещё с опечаткой) не нужно.
function cleanMeetingTitle(t: string): string {
  return t.replace(/\s*\([^)]*(?:бриф|защит)[^)]*\)\s*$/i, '').trim() || t;
}

function fmtRevenue(rub: number): string {
  if (rub >= 1_000_000_000) return `${(rub / 1_000_000_000).toFixed(rub % 1_000_000_000 ? 1 : 0)} млрд ₽`;
  if (rub >= 1_000_000) return `${Math.round(rub / 1_000_000)} млн ₽`;
  if (rub >= 1_000) return `${Math.round(rub / 1_000)} тыс ₽`;
  return `${rub} ₽`;
}

/** День недели и его номер (0=вс) по дате встречи в МСК. */
function weekdayMsk(at: string): { wd: string; weekend: boolean } | null {
  try {
    const msk = new Date(new Date(at).toLocaleString('en-US', { timeZone: 'Europe/Moscow' }));
    const n = msk.getDay(); // 0=вс … 6=сб
    return { wd: WEEKDAYS[n], weekend: n === 0 || n === 6 };
  } catch { return null; }
}

/**
 * Строка встречи. showDate=true → колонка дата+день недели (для назначенных на
 * другую дату); иначе только время. Выручку показываем только для ТМ-брифингов.
 */
const PILL: React.CSSProperties = { display: 'inline-block', fontSize: 11, fontWeight: 600, borderRadius: 999, padding: '3px 9px', whiteSpace: 'nowrap', lineHeight: 1.5 };
const REV_CHIP: React.CSSProperties = { ...PILL, fontWeight: 700, background: '#fff', border: '1px solid var(--bb-line)', color: 'var(--bb-ink)' };
const REV_CHIP_LOW: React.CSSProperties = { ...PILL, fontWeight: 700, background: '#fdeced', color: 'var(--bb-red)' };
const TIMECOL: React.CSSProperties = { fontWeight: 600, fontSize: 13, color: 'var(--bb-violet)', flex: '0 0 auto' };

function MeetingRow({ m, showDate }: { m: LiveMeeting; showDate: boolean }) {
  const st = STATUS_PILL[m.status] ?? STATUS_PILL.scheduled;
  const ty = m.type ? MEETING_TYPE[m.type] : null;
  const showRevenue = m.type === 'briefing' && m.creatorIsTm && m.companyRevenue != null;
  const low = showRevenue && (m.companyRevenue as number) < REVENUE_LOW_THRESHOLD;
  const wk = showDate ? weekdayMsk(m.at) : null;
  return (
    <li className="bb-alert-row" style={{ gap: 14, alignItems: 'flex-start' }}>
      {showDate ? (
        <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.35, minWidth: 52, flex: '0 0 auto' }}>
          <b className="tabular" style={TIMECOL}>{fmtDate2(m.at)}</b>
          {wk ? <span style={{ fontSize: 11, fontWeight: 600, color: wk.weekend ? 'var(--bb-red)' : 'var(--bb-faint)' }}>{wk.wd}</span> : null}
        </span>
      ) : (
        <span className="tabular" style={{ ...TIMECOL, minWidth: 46 }}>{timeOnly(m.at) || '—'}</span>
      )}
      <div style={{ minWidth: 0, flex: 1 }}>
        {m.id ? <a className="bb-alert-title" href={spUrl(1048, m.id)} target="_blank" rel="noopener noreferrer">{cleanMeetingTitle(m.title)} <ExternalLink size={12} /></a> : <span style={{ fontWeight: 600, fontSize: 14 }}>{cleanMeetingTitle(m.title)}</span>}
        <p className="bb-alert-meta">
          {ty ? <span style={{ ...PILL, background: ty.bg, color: ty.color }}>{ty.label}</span> : null}
          <span>· {m.manager}</span>
          {showRevenue ? <span style={low ? REV_CHIP_LOW : REV_CHIP}>выручка {fmtRevenue(m.companyRevenue as number)}</span> : null}
        </p>
      </div>
      {showDate ? (
        <span className="tabular" style={{ ...TIMECOL, paddingTop: 1, whiteSpace: 'nowrap' }}>{timeOnly(m.at)}</span>
      ) : (
        <span style={{ ...PILL, background: st.bg, color: st.color, flex: '0 0 auto' }}>{st.label}</span>
      )}
    </li>
  );
}

function fmtDate2(at: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(at));
  } catch { return ''; }
}

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
  const todayMsk = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date());
  // принимаем любую дату в диапазоне [DATA_START; сегодня); сегодня = live
  const raw = typeof params.date === 'string' ? params.date : '';
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw));
  const selected = validDate && raw >= DATA_START && raw < todayMsk ? raw : null;
  const isArchive = selected !== null;

  const data: LiveData | null = isArchive ? await getDayBreakdown(selected) : await getLive();
  const empty = !data || (!isArchive && data.updatedAt === null);
  // Live-снимок не за сегодня (выходной / cron не отработал) — не выдаём его за «Сегодня».
  const stale = !isArchive && !empty && !!data?.reportDate && data.reportDate !== todayMsk;

  const t = data?.totals;
  const connect = t && t.dials ? Math.round((t.answered / t.dials) * 100) : 0;

  // Разбиение встреч: «проводятся в этот день» vs «назначены сегодня на другую дату».
  const refDay = isArchive ? (selected as string) : todayMsk;
  const meetingDay = (at: string): string => {
    if (!at) return '';
    try { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date(at)); } catch { return ''; }
  };
  const allMeetings = data?.meetings ?? [];
  const meetingsSetOther = allMeetings.filter((m) => m.setToday && meetingDay(m.at) !== refDay);
  const meetingsHappening = allMeetings.filter((m) => !(m.setToday && meetingDay(m.at) !== refDay));
  const hasSetOther = meetingsSetOther.length > 0;

  // «КП получено» = только ГОТОВЫЕ (status success). КП в работе и отклонённые
  // (Не актуально) сюда не входят — отклонённые видны в Ленте (фильтр КП).
  const kpClosed = (data?.kp ?? []).filter((k) => k.status === 'success');

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #3a3780, #5b50d6)' }}>
        <div className="bb-hero-row" style={{ alignItems: 'flex-start', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">{isArchive ? 'Отдел продаж · день из архива' : stale ? 'Отдел продаж · нет свежего снимка' : 'Отдел продаж · реальное время'}</div>
            <h1 className="bb-hero-title">
              {isArchive
                ? `День ${fmtDay(selected)}`
                : stale
                  ? `Последний рабочий день ${fmtDay(data!.reportDate!)}`
                  : <><span className="bb-live-dot" style={{ marginRight: 10 }} />Сегодня</>}
            </h1>
            <div className="bb-hero-sub">
              {isArchive
                ? 'сохранённый разбор за выбранный день (чаты — только в режиме «Сегодня»)'
                : stale
                  ? `сегодня (${fmtDay(todayMsk)}) сбор не идёт — нерабочий день или ещё не было прогона · снимок за ${fmtDay(data!.reportDate!)}, обновлён ${fmtMsk(data!.updatedAt)} МСК`
                  : (data?.updatedAt ? `обновлено ${fmtMsk(data.updatedAt)} МСК · каждые ~20 мин в рабочие часы` : 'данные ещё не собраны')}
            </div>
          </div>
          <div style={{ flex: '0 0 auto', paddingTop: 4 }}>
            <DaySelect selected={selected} minDate={DATA_START} maxDate={todayMsk} />
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
            <Tile icon={<CalendarClock size={14} />} label="Назначено · телемаркетинг" value={t.meetingsSetTm} sub="встречи, назначенные ТМ за день" />
            <Tile icon={<FileText size={14} />} label="Брифы" value={t.briefs} />
            <Tile icon={<FileText size={14} />} label="КП получено" value={kpClosed.length} sub="готовые КП за день" />
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

          {/* Ряд 1: встречи сегодня / назначены на другую дату */}
          <div className="bb-grid k2" style={{ gridTemplateColumns: hasSetOther ? '1fr 1fr' : '1fr', gap: 16 }}>
            <div className="bb-card">
              <div className="bb-sect-head"><span className="bb-sect-ic"><CalendarClock size={17} /></span><h2>Встречи{isArchive ? '' : ' сегодня'}</h2><small>{t.meetingsHeld} провед. · {t.meetingsScheduled} назнач. · {t.meetingsCancelled} отмен.</small></div>
              {meetingsHappening.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>Встреч нет.</p>
              ) : (
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
                  {meetingsHappening.map((m, i) => <MeetingRow key={`h${i}`} m={m} showDate={false} />)}
                </ul>
              )}
            </div>

            {hasSetOther ? (
              <div className="bb-card">
                <div className="bb-sect-head"><span className="bb-sect-ic"><CalendarClock size={17} /></span><h2>Встречи назначены</h2><small>сегодня назначили на другую дату · {meetingsSetOther.length}</small></div>
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
                  {meetingsSetOther.map((m, i) => <MeetingRow key={`o${i}`} m={m} showDate={true} />)}
                </ul>
              </div>
            ) : null}
          </div>

          {/* Ряд 2: брифы / КП */}
          <div className="bb-grid k2" style={{ gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
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
                      {b.service
                        ? <span className="bb-reason" style={{ background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>{b.service}</span>
                        : <span className="bb-reason" style={{ background: 'transparent', color: 'var(--bb-faint)', border: '1px dashed var(--bb-line)' }}>— услуга</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="bb-card">
              <div className="bb-sect-head"><span className="bb-sect-ic"><FileText size={17} /></span><h2>КП получено</h2><small>{kpClosed.length}</small></div>
              {kpClosed.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>КП нет.</p>
              ) : (
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
                  {kpClosed.map((k, i) => (
                    <li key={i} className="bb-alert-row" style={{ gap: 10 }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        {k.id ? <a className="bb-alert-title" href={spUrlKp(k.id)} target="_blank" rel="noopener noreferrer">{k.title} <ExternalLink size={12} /></a> : <span style={{ fontWeight: 600, fontSize: 14 }}>{k.title}</span>}
                        <p className="bb-alert-meta">
                          {k.manager}
                          {k.dealId ? <> · <a href={dealUrl(k.dealId)} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--bb-violet)' }}>сделка</a></> : null}
                        </p>
                      </div>
                      <span style={{ display: 'inline-flex', gap: 6, flex: '0 0 auto', alignItems: 'center' }}>
                        {k.status === 'rejected' ? <span className="bb-reason" style={{ background: '#fdeced', color: 'var(--bb-red)' }}>Отклонено</span> : null}
                        {k.service
                          ? <span className="bb-reason" style={{ background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>{k.service}</span>
                          : <span className="bb-reason" style={{ background: 'transparent', color: 'var(--bb-faint)', border: '1px dashed var(--bb-line)' }}>— услуга</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Лента событий дня (кликабельна + фильтр) */}
          <FeedView items={data!.feed} isArchive={isArchive} />
        </>
      )}
    </div>
  );
}
