import { CalendarView } from '@/components/CalendarView';
import { availableReportDates } from '@/lib/reports';

export default async function DailyOPReportPage() {
  const dates = await availableReportDates();

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 px-8 py-10">
      <header className="border-b border-[#e8e4f2] pb-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-[#5b50d6]">Командный центр</p>
        <h1 className="mt-1 text-2xl font-extrabold text-[#1a1f3a]">Дневной отчет ОП</h1>
      </header>

      <section className="grid gap-6">
        <div>
          <h2 className="text-xl font-extrabold text-[#1a1f3a]">Архив отчётов</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#6b6f88]">
            Выберите дату с готовым отчётом. Серые дни пока недоступны.
          </p>
        </div>
        <CalendarView availableDates={dates} />
      </section>
    </div>
  );
}
