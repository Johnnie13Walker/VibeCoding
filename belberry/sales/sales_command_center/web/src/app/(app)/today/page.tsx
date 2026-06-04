import { PhoneCall, PhoneForwarded, Timer, Handshake, FileText, Zap, Activity } from 'lucide-react';
import { getLive } from '@/lib/live';

export const dynamic = 'force-dynamic';

function fmtMsk(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
function timeOnly(at: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(at));
  } catch {
    return '';
  }
}

function Tile({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="bb-card" style={{ padding: 18 }}>
      <div style={{ fontSize: 12, color: 'var(--bb-muted)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: 'var(--bb-violet)', display: 'inline-flex' }}>{icon}</span>
        {label}
      </div>
      <div className="tabular" style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.03em', marginTop: 8 }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

const FEED_ICON = { meeting: <Handshake size={16} />, kp: <FileText size={16} />, deal: <Zap size={16} /> };
const FEED_LABEL = { meeting: 'встреча', kp: 'КП', deal: 'сделка' };

export default async function TodayPage() {
  const data = await getLive();
  const t = data.totals;
  const connect = t.dials ? Math.round((t.answered / t.dials) * 100) : 0;

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #3a3780, #5b50d6)' }}>
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Отдел продаж · реальное время</div>
            <h1 className="bb-hero-title"><span className="bb-live-dot" style={{ marginRight: 10 }} />Сегодня</h1>
            <div className="bb-hero-sub">
              {data.updatedAt ? `обновлено ${fmtMsk(data.updatedAt)} МСК · каждые ~20 мин в рабочие часы` : 'данные ещё не собраны'}
            </div>
          </div>
        </div>
      </div>

      {data.updatedAt === null ? (
        <div className="bb-card"><p style={{ color: 'var(--bb-muted)' }}>Снимок текущего дня ещё не сформирован. Появится после ближайшего сбора.</p></div>
      ) : (
        <>
          <div className="bb-grid bb-grid-4" style={{ marginBottom: 16 }}>
            <Tile icon={<PhoneCall size={14} />} label="Наборы" value={t.dials} />
            <Tile icon={<PhoneForwarded size={14} />} label="Дозвоны" value={t.answered} sub={`${connect}% конверсия`} />
            <Tile icon={<Timer size={14} />} label="Звонки 120с+" value={t.calls120} />
            <Tile icon={<Handshake size={14} />} label="Встречи сегодня" value={t.meetings} />
            <Tile icon={<FileText size={14} />} label="КП сегодня" value={t.kp} />
            <Tile icon={<Zap size={14} />} label="Сделок создано" value={t.deals} />
          </div>

          <div className="bb-grid k2" style={{ gridTemplateColumns: '1.3fr 1fr', gap: 16 }}>
            <div className="bb-card">
              <div className="bb-sect-head"><span className="bb-sect-ic"><Activity size={17} /></span><h2>По менеджерам</h2><small>{data.managers.length}</small></div>
              {data.managers.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>Активности пока нет.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="bb-table">
                    <thead><tr><th>Менеджер</th><th className="r">Наборы</th><th className="r">Дозвоны</th><th className="r">120с+</th><th className="r">Встречи</th><th className="r">КП</th></tr></thead>
                    <tbody>
                      {data.managers.map((m) => (
                        <tr key={m.managerId}>
                          <td style={{ fontWeight: 600 }}>{m.name}</td>
                          <td className="r">{m.dials}</td>
                          <td className="r">{m.answered}</td>
                          <td className="r">{m.calls120}</td>
                          <td className="r">{m.meetings}</td>
                          <td className="r">{m.kp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="bb-card">
              <div className="bb-sect-head"><span className="bb-sect-ic"><Activity size={17} /></span><h2>Лента</h2></div>
              {data.feed.length === 0 ? (
                <p style={{ color: 'var(--bb-muted)' }}>Событий пока нет.</p>
              ) : (
                <div className="pill-list" style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {data.feed.map((e, i) => (
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
          </div>
        </>
      )}
    </div>
  );
}
