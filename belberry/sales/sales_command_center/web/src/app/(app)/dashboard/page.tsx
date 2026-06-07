import Link from 'next/link';
import { Filter, FileText, TrendingUp, Target, Activity, ArrowLeftRight, Users, Phone, Mail, Clock, BarChart3, CalendarDays, Goal, XCircle } from 'lucide-react';
import { FunnelBars } from '@/components/dashboard/FunnelBars';
import { SalesFunnel } from '@/components/dashboard/SalesFunnel';
import { ForecastView } from '@/components/dashboard/Forecast';
import { OperationalMatrixView } from '@/components/dashboard/OperationalMatrix';
import { ManagerConversions } from '@/components/dashboard/ManagerConversions';
import { ManagerPipelineView } from '@/components/dashboard/ManagerPipeline';
import { TmActivityView } from '@/components/dashboard/TmActivity';
import { MessagingView } from '@/components/dashboard/Messaging';
import { VelocityView } from '@/components/dashboard/Velocity';
import { MonthlyDynamics } from '@/components/dashboard/MonthlyDynamics';
import { Day2DayView } from '@/components/dashboard/Day2Day';
import { PlanFactView } from '@/components/dashboard/PlanFact';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { Gauge } from '@/components/dashboard/Gauge';
import { SalesRejectionsView } from '@/components/dashboard/SalesRejections';
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

      {/* Прогноз закрытия месяца + pacing (КД-хедлайн) */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Target size={17} />} title="Прогноз закрытия месяца" hint="взвешенная воронка + темп" />
        <ForecastView data={data.forecast} />
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

      {/* Операционная эффективность — «Опер» по дням (детальное качество встреч — на /meetings) */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Activity size={17} />} title="Операционная эффективность" hint="модель реальных рабочих минут · балл 0–10 по дням" />
        <OperationalMatrixView data={data.operational} />
      </div>

      {/* Конверсии по менеджерам */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<ArrowLeftRight size={17} />} title="Конверсии по менеджерам" hint={per} />
        <ManagerConversions data={data.managerConversions} />
      </div>

      {/* Отказы — динамика с начала года (воронка Продажи, C10:LOSE) + мультиселект МП */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<XCircle size={17} />} title="Отказы — динамика с начала года" hint={`воронка Продажи · ${data.salesRejections.yearLabel}`} />
        <SalesRejectionsView data={data.salesRejections} />
      </div>

      {/* Воронка по менеджерам · текущее состояние + Δ за месяц */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Users size={17} />} title="Воронка по менеджерам" hint="снимок + изменение за месяц" />
        <ManagerPipelineView data={data.managerPipeline} />
      </div>

      {/* Активность ТМ · звонки */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Phone size={17} />} title="Активность ТМ · звонки" hint={per} />
        <TmActivityView data={data.tmActivity} />
      </div>

      {/* Мессенджеры и почта */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Mail size={17} />} title="Мессенджеры и почта" hint={per} />
        <MessagingView data={data.messaging} />
      </div>

      {/* Скорость воронки + деньги по возрасту */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Clock size={17} />} title="Скорость воронки и деньги по возрасту" hint={`снимок ${data.snapshotDate ?? '—'}`} />
        <VelocityView data={data.velocity} />
      </div>

      {/* Помесячная динамика */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<BarChart3 size={17} />} title="Помесячная динамика" hint="последние 6 месяцев" />
        <MonthlyDynamics data={data.monthly} />
      </div>

      {/* Day2Day — дневные итоги месяца */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<CalendarDays size={17} />} title="Day2Day" hint={`${data.monthLabel} · по дням`} />
        <Day2DayView data={data.day2day} />
      </div>

      {/* План / факт */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <SectionHead icon={<Goal size={17} />} title="План / факт" hint={data.monthLabel} />
        <PlanFactView data={data.planFact} />
      </div>

      {/* Дальше: win rate + источники (нужна мелкая правка раннера). */}
    </div>
  );
}
