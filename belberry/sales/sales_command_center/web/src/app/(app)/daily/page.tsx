import { DayReportView } from '@/components/DayReportView';
import { availableReportDates } from '@/lib/reports';

export default async function DailyOPReportPage() {
  const dates = await availableReportDates();

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
        <DayReportView availableDates={dates} />
      </div>
    </div>
  );
}
