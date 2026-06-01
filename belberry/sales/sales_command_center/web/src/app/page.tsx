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
      <header className="flex items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <p className="text-sm font-medium text-slate-500">Global Sales</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">Командный центр продаж</h1>
        </div>
        <form action="/api/auth/logout" method="post">
          <button className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50">
            Выйти
          </button>
        </form>
      </header>

      <section className="grid gap-6">
        <div>
          <h2 className="text-xl font-semibold text-slate-950">Архив отчётов</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Выберите дату с готовым отчётом. Серые дни пока недоступны.
          </p>
        </div>
        <CalendarView availableDates={dates} />
      </section>
    </main>
  );
}
