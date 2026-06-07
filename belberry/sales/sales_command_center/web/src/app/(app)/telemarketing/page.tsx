import Link from 'next/link';
import { Phone, Users, Filter, CalendarCheck, ListTree, BarChart3, Goal, Mail, Search, Sparkles, Coins, Clock, Bell, PhoneOutgoing } from 'lucide-react';
import { TmFunnel50View } from '@/components/telemarketing/TmFunnel';
import { TmMonthly } from '@/components/telemarketing/TmMonthly';
import { TmDialsHeatmap } from '@/components/telemarketing/TmDialsHeatmap';
import {
  TmKpiGrid,
  TmManagerTable,
  TmMeetingsResultView,
  TmMicroFunnelsView,
  TmPlanFactView,
  TmOutreachView,
  TmRejectionsView,
  TmHeatmapView,
  TmMeetingQualityView,
  TmAlertsView,
  SoonCard,
} from '@/components/telemarketing/blocks';
import { getTmDashboardData } from '@/lib/telemarketing';

export const dynamic = 'force-dynamic';

function fmtMsk(iso: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function SectionHead({ icon, title, hint, right }: { icon: React.ReactNode; title: string; hint?: string; right?: React.ReactNode }) {
  return (
    <div className="bb-sect-head">
      <span className="bb-sect-ic">{icon}</span>
      <h2>{title}</h2>
      {hint ? <small>{hint}</small> : null}
      {right ?? null}
    </div>
  );
}

export default async function TelemarketingPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string; month?: string }>;
}) {
  const params = await searchParams;
  const range: 'month' | 'week' = params.period === 'week' ? 'week' : 'month';
  const monthParam = params.month && /^\d{4}-\d{2}$/.test(params.month) ? params.month : null;
  const data = await getTmDashboardData(range, monthParam);

  const periodHref = (p: 'month' | 'week') => `/telemarketing?period=${p}`;
  const monthHref = (ym: string) => `/telemarketing?month=${ym}`;

  return (
    <div className="bb-page bb-fade">
      {/* HERO */}
      <div className="bb-hero">
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Командный центр · Телемаркетинг</div>
            <h1 className="bb-hero-title">Дашборд ТМ</h1>
            <div className="bb-hero-sub">
              Работа отдела телемаркетинга: обзвон, назначение встреч, ТМ-воронка [50]
              {data.snapshotDate ? ` · снимок ${data.snapshotDate}` : ''}
              {data.generatedAt ? ` · отчёт ${fmtMsk(data.generatedAt)} МСК` : ''}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14, flexWrap: 'wrap' }}>
              <div className="bb-seg">
                <Link href={periodHref('month')} className={range === 'month' && !data.selectedMonth ? 'on' : ''}>Месяц</Link>
                <Link href={periodHref('week')} className={range === 'week' && !data.selectedMonth ? 'on' : ''}>Неделя</Link>
              </div>
              {data.monthOptions.length > 0 ? (
                <div className="bb-seg">
                  {data.monthOptions.map((mo) => (
                    <Link key={mo.ym} href={monthHref(mo.ym)} className={data.selectedMonth === mo.ym ? 'on' : ''}>{mo.label}</Link>
                  ))}
                </div>
              ) : null}
              <span style={{ color: '#c9c5f0', fontSize: 13 }}>{data.periodLabel}</span>
            </div>
          </div>
        </div>
      </div>

      {data.managers.length === 0 ? (
        <div className="bb-card">
          <p style={{ color: 'var(--bb-muted)' }}>
            Нет сотрудников телемаркетинга за период (scope по должности «телемаркетолог»). Проверьте справочник
            сотрудников и сбор активности.
          </p>
        </div>
      ) : (
        <>
          {/* A. KPI обзвона */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Phone size={17} />} title="Обзвон · итог отдела" hint={`${data.monthLabel} · ${data.kpis.zvonari} телемаркетолога`} />
            <TmKpiGrid kpis={data.kpis} kpisPrev={data.kpisPrev} cmpLabel={data.kpisCmpLabel} />
          </div>

          {/* План / факт ТМ — сразу после итога обзвона */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Goal size={17} />} title="План / факт ТМ" hint={`${data.monthLabel} · дозвоны + брифования`} />
            <TmPlanFactView data={data.planFact} />
          </div>

          {/* B. По звонарям */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Users size={17} />} title="По телемаркетологам" hint={data.monthLabel} />
            <TmManagerTable rows={data.table} />
          </div>

          {/* C + D: ТМ-воронка cat50 + Встречи→результат */}
          <div className="bb-grid bb-grid-2" style={{ marginBottom: 16 }}>
            <div className="bb-card">
              <SectionHead icon={<Filter size={17} />} title="ТМ-воронка [50]" hint={`снимок ${data.snapshotDate ?? '—'}`} />
              <TmFunnel50View data={data.funnel50} />
            </div>
            <div className="bb-card">
              <SectionHead icon={<CalendarCheck size={17} />} title="Встречи → результат" hint={data.monthLabel} />
              <TmMeetingsResultView result={data.meetingsResult} />
            </div>
          </div>

          {/* F. Динамика по месяцам — мультиселект звонарей + сравнение «на эту дату» */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<BarChart3 size={17} />} title="Динамика по месяцам" hint="мультиселект · текущий vs прошлый на ту же дату" />
            <p style={{ fontSize: 12, color: 'var(--bb-faint)', margin: '-6px 0 14px' }}>
              Выберите одного или нескольких телемаркетологов — данные суммируются. По умолчанию выбраны все. Дашборд охватывает любого сотрудника ТМ (по должности), список не захардкожен.
            </p>
            <TmMonthly data={data.monthlyBundle} />
          </div>

          {/* Причины отвала (накопленно, личные закрытия) */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Search size={17} />} title="Причины отвала" hint="накопленно · личные закрытия" />
            <TmRejectionsView rejections={data.rejections} />
          </div>

          {/* G. Outreach */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Mail size={17} />} title="Outreach — другие касания" hint={data.monthLabel} />
            <TmOutreachView outreach={data.outreach} />
          </div>

          {/* Микро-воронка звонка */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<ListTree size={17} />} title="Микро-воронка звонка — где теряется" hint={`${data.monthLabel} · по телемаркетологу`} />
            <TmMicroFunnelsView funnels={data.microFunnels} />
          </div>

          {/* Fast-follow блоки */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Sparkles size={17} />} title="Качество встреч от ТМ" hint="из разбора «Анализ встреч»" />
            <TmMeetingQualityView quality={data.meetingQuality} />
          </div>
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Coins size={17} />} title="Окупаемость ТМ — встречи → Продажи → деньги" hint="когорта" />
            <SoonCard title="Downstream-ценность холодных встреч" desc="Из назначенных ТМ встреч — сколько в Продажи, КП, оплат и на какую сумму. Нужна связка cat50 → cat10." />
          </div>
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Clock size={17} />} title="Когда берут трубку" hint="час × день недели · за 3 месяца" />
            <TmHeatmapView heatmap={data.heatmap} />
          </div>

          {/* Карта активности набора — когда звонари делают наборы */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<PhoneOutgoing size={17} />} title="Когда звонят — активность набора" hint="час × день недели · за 3 месяца" />
            <TmDialsHeatmap data={data.dialsHeatmap} />
          </div>

          {/* ТМ-алерты */}
          <div className="bb-card" style={{ marginBottom: 16 }}>
            <SectionHead icon={<Bell size={17} />} title="Сигналы по ТМ" hint="авто" />
            <TmAlertsView alerts={data.alerts} />
          </div>

          <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 24 }}>
            Воронка [50] «Телемаркетинг» · дозвон = разговор ≥60с (Voximplant) · встреча «назначено» — создателю (ТМ) ·
            scope по должности · время Europe/Moscow. Блоки «скоро» требуют доработки раннера.
          </p>
        </>
      )}
    </div>
  );
}
