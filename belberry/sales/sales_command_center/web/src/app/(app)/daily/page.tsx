import { CalendarView } from '@/components/CalendarView';
import { availableReportDates } from '@/lib/reports';

export default async function DailyOPReportPage() {
  const dates = await availableReportDates();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-12 px-10 py-14">
      <header className="space-y-1.5">
        <p className="text-sm font-medium text-[#6e6e73]">Командный центр</p>
        <h1 className="text-[2.1rem] font-semibold leading-tight tracking-[-0.022em] text-[#1d1d1f]">
          Дневной отчет ОП
        </h1>
      </header>

      <section className="space-y-5">
        <div className="space-y-1.5">
          <h2 className="text-xl font-semibold tracking-[-0.018em] text-[#1d1d1f]">Архив отчётов</h2>
          <p className="max-w-xl text-[0.95rem] leading-relaxed text-[#6e6e73]">
            Выберите дату с готовым отчётом. Серые дни пока недоступны.
          </p>
        </div>
        <CalendarView availableDates={dates} />
      </section>
    </div>
  );
}
