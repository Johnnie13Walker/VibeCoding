import { DayReportView } from '@/components/DayReportView';
import { availableReportDates } from '@/lib/reports';

export default async function DailyOPReportPage({
  searchParams,
}: {
  searchParams: Promise<{ open?: string; date?: string }>;
}) {
  const dates = await availableReportDates();
  const params = await searchParams;
  const requested = params.date && dates.includes(params.date) ? params.date : undefined;
  const initialDate = requested ?? (params.open === 'last' ? dates[0] : undefined);

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora">
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Командный центр</div>
            <h1 className="bb-hero-title">Дневной отчёт ОП</h1>
            <div className="bb-hero-sub">Выберите день — богатый разбор откроется прямо здесь</div>
          </div>
        </div>
      </div>

      <div className="bb-card">
        <DayReportView availableDates={dates} initialDate={initialDate} />
      </div>
    </div>
  );
}
