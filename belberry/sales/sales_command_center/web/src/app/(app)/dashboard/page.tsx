import { Wallet, Handshake, PhoneCall, Zap, Filter, Flame, Users, Goal } from 'lucide-react';
import { FunnelChart } from '@/components/dashboard/FunnelChart';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { Gauge } from '@/components/dashboard/Gauge';
import { getDashboardData } from '@/lib/dashboard';

export const dynamic = 'force-dynamic';

function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

function SectionHead({ icon, title, hint }: { icon: React.ReactNode; title: string; hint?: string }) {
  return (
    <div className="bb-sect-head">
      <span className="bb-sect-ic">{icon}</span>
      <h2>{title}</h2>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}

export default async function DashboardPage() {
  const data = await getDashboardData();
  const meetingsTrend = data.trend.map((t) => t.meetings);
  const dialsTrend = data.trend.map((t) => t.dials);

  return (
    <div className="bb-page bb-fade">
      {/* HERO с aurora + health-gauge */}
      <div className="bb-hero bb-aurora">
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Отдел продаж · {data.monthLabel}</div>
            <h1 className="bb-hero-title">Командный центр</h1>
            <div className="bb-hero-sub">
              Снимок воронки {data.snapshotDate ?? '—'} · {data.funnelCount} открытых сделок на {rub(data.funnelAmount)}
            </div>
          </div>
          <Gauge value={data.health} label="здоровье" />
        </div>
      </div>

      {/* KPI */}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 22 }}>
        <KpiCard label="Сумма воронки" value={data.funnelAmount} fmt={rub} Icon={Wallet} />
        <KpiCard label="Встречи за месяц" value={data.meetingsHeldTotal} Icon={Handshake} delta={data.deltas.meetings} trend={meetingsTrend} />
        <KpiCard label="Наборы за месяц" value={data.dialsTotal} Icon={PhoneCall} delta={data.deltas.dials} trend={dialsTrend} />
        <KpiCard label="Сделок создано" value={data.dealsCreatedTotal} Icon={Zap} delta={data.deltas.deals} />
      </div>

      {/* Воронка + затор */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Filter size={17} />} title="Воронка продаж" hint={`снимок ${data.snapshotDate ?? '—'}`} />
        <FunnelChart data={data.funnel} />

        {data.stuck.length > 0 ? (
          <div style={{ marginTop: 22, borderTop: '1px solid var(--bb-line)', paddingTop: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Flame size={16} color="#d4202e" />
              <h3 style={{ fontSize: 14.5, fontWeight: 700 }}>Застрявшие сделки</h3>
              <small style={{ color: 'var(--bb-faint)', fontSize: 12.5 }}>дольше всего без движения</small>
            </div>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
              {data.stuck.map((d) => (
                <li key={d.dealId} className="bb-stuck-row">
                  <div style={{ minWidth: 0 }}>
                    <p className="bb-ellipsis" style={{ fontSize: 14, fontWeight: 600 }}>{d.title}</p>
                    <p style={{ fontSize: 12, color: 'var(--bb-faint)' }}>{d.stageLabel} · {d.manager}</p>
                  </div>
                  <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                    <p className="tabular" style={{ fontSize: 14, fontWeight: 700 }}>{rub(d.amount)}</p>
                    <p style={{ fontSize: 12, fontWeight: 600, color: '#d4202e' }}>{d.stuckDays} дн. без движения</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {/* Команда */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Users size={17} />} title="Команда" hint={`активность за ${data.monthLabel}`} />
        {data.team.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Нет данных активности за период.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="bb-table">
              <thead>
                <tr>
                  <th>Менеджер</th>
                  <th className="r">Встречи</th>
                  <th className="r">Наборы</th>
                  <th className="r">120с+</th>
                  <th className="r">КП</th>
                  <th className="r">Сделок</th>
                  <th className="r">Часы</th>
                </tr>
              </thead>
              <tbody>
                {data.team.map((m) => (
                  <tr key={m.managerId}>
                    <td style={{ fontWeight: 600 }}>{m.name}</td>
                    <td className="r">
                      <span style={{ fontWeight: m.meetingsHeld >= data.meetingsPlan ? 700 : 400, color: m.meetingsHeld >= data.meetingsPlan ? '#2c7a4a' : 'var(--bb-ink)' }}>
                        {m.meetingsHeld}
                      </span>
                    </td>
                    <td className="r">{m.dials}</td>
                    <td className="r">{m.calls120}</td>
                    <td className="r">{m.kpSent}</td>
                    <td className="r">{m.dealsCreated}</td>
                    <td className="r">{m.talkHours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* План / факт */}
      {data.team.length > 0 ? (
        <div className="bb-card" style={{ marginBottom: 16 }}>
          <SectionHead icon={<Goal size={17} />} title="План / факт встреч" hint={`цель ${data.meetingsPlan}/чел`} />
          <div className="bb-grid" style={{ gridTemplateColumns: 'repeat(2,1fr)', gap: 16 }}>
            {data.team.slice(0, 4).map((m) => {
              const pct = Math.min(100, Math.round((m.meetingsHeld / data.meetingsPlan) * 100));
              return (
                <div key={m.managerId}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, fontWeight: 600 }}>
                    <span>{m.name}</span>
                    <span className="tabular" style={{ color: 'var(--bb-muted)' }}>{m.meetingsHeld} / {data.meetingsPlan}</span>
                  </div>
                  <div className="bb-pf-bar"><i style={{ width: `${pct}%` }} /></div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
