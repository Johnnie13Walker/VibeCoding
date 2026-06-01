import { redirect } from 'next/navigation';
import { requireSession } from '@/lib/auth';

export default async function HomePage() {
  const session = await requireSession();

  if (!session) {
    redirect('/login');
  }

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

      <section className="grid gap-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-xl font-semibold text-slate-950">Доступ открыт</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Календарь и отчёты дня появятся в следующей фазе. Сейчас проверяем
            закрытый вход, сессию и базовую оболочку.
          </p>
        </div>
        <dl className="grid gap-3 text-sm text-slate-700 sm:grid-cols-3">
          <div>
            <dt className="font-medium text-slate-500">Bitrix ID</dt>
            <dd className="mt-1 font-semibold text-slate-950">{session.bitrixId}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Email</dt>
            <dd className="mt-1 font-semibold text-slate-950">{session.email}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Роль</dt>
            <dd className="mt-1 font-semibold text-slate-950">{session.role}</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
