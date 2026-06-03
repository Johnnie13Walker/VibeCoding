import { redirect } from 'next/navigation';
import { CalendarView } from '@/components/CalendarView';
import { requireSession } from '@/lib/auth';
import { availableReportDates } from '@/lib/reports';

export default async function HomePage() {
  const session = await requireSession();

  if (!session) {
    redirect('/login');
  }
  const dates = await availableReportDates();

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-6 py-10">
      <header className="flex items-center justify-between gap-4 border-b border-[#e8e4f2] pb-5">
        <div className="flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/belberry-logo.svg" alt="Belberry" className="h-8 w-auto" />
          <div className="border-l border-[#e8e4f2] pl-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-[#5b50d6]">Командный центр</p>
            <h1 className="mt-1 text-2xl font-extrabold text-[#1a1f3a]">Сводки отдела продаж</h1>
          </div>
        </div>
        <form action="/api/auth/logout" method="post">
          <button className="rounded-lg border border-[#cfc8f3] bg-white px-4 py-2 text-sm font-semibold text-[#5b50d6] shadow-sm transition hover:bg-[#f3effc]">
            Выйти
          </button>
        </form>
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
    </main>
  );
}
