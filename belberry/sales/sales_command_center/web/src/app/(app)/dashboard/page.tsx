import Link from 'next/link';
import { Filter, FileText, TrendingUp } from 'lucide-react';
import { FunnelBars } from '@/components/dashboard/FunnelBars';
import { SalesFunnel } from '@/components/dashboard/SalesFunnel';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { Gauge } from '@/components/dashboard/Gauge';
import { getDashboardData } from '@/lib/dashboard';

export const dynamic = 'force-dynamic';

function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

function fmtMsk(iso: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
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

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string }>;
}) {
  const params = await searchParams;
  const range: 'month' | 'week' = params.period === 'week' ? 'week' : 'month';
  const data = await getDashboardData(range);
  const meetingsTrend = data.trend.map((t) => t.meetings);
  const dialsTrend = data.trend.map((t) => t.dials);
  const per = range === 'week' ? 'за 7 дней' : 'за месяц';

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
              {data.generatedAt ? ` · отчёт сформирован ${fmtMsk(data.generatedAt)} МСК` : ''}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14, flexWrap: 'wrap' }}>
              <div className="bb-seg">
                <Link href="/dashboard?period=month" className={range === 'month' ? 'on' : ''}>Месяц</Link>
                <Link href="/dashboard?period=week" className={range === 'week' ? 'on' : ''}>Неделя</Link>
              </div>
              <Link href="/daily?open=last" className="bb-hero-btn" style={{ marginTop: 0 }}>
                <FileText size={15} /> Открыть последний отчёт
              </Link>
            </div>
          </div>
          <Gauge value={data.health} label="здоровье" />
        </div>
      </div>

      {/* KPI */}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 22 }}>
        <KpiCard label="Сумма воронки" value={data.funnelAmount} money icon="wallet" />
        <KpiCard label={`Встречи ${per}`} value={data.meetingsHeldTotal} icon="handshake" delta={data.deltas.meetings} trend={meetingsTrend} />
        <KpiCard label={`Наборы ${per}`} value={data.dialsTotal} icon="phone" delta={data.deltas.dials} trend={dialsTrend} />
        <KpiCard label={`Сделки ${per}`} value={data.dealsCreatedTotal} icon="zap" delta={data.deltas.deals} />
      </div>

      {/* Воронка продаж — снимок открытых сделок по стадиям */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Filter size={17} />} title="Воронка продаж" hint={`снимок ${data.snapshotDate ?? '—'}`} />
        <FunnelBars data={data.funnel} />
      </div>

      {/* Путь сделки вход→оплата — поток за период с конверсиями */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<TrendingUp size={17} />} title="Путь сделки: вход → оплата" hint={per} />
        <SalesFunnel data={data.salesFunnel} />
      </div>

      {/* Ниже будут новые блоки v1: помесячная динамика/Day2Day, план/факт. */}
    </div>
  );
}
