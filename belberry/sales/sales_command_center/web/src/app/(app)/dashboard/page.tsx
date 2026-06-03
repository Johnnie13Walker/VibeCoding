export default function DashboardPage() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 px-8 py-10">
      <header className="border-b border-[#e8e4f2] pb-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-[#5b50d6]">Платформа</p>
        <h1 className="mt-1 text-2xl font-extrabold text-[#1a1f3a]">Dashboard</h1>
      </header>

      <div className="flex min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-[#cfc8f3] bg-white/60 px-6 text-center">
        <div className="text-4xl" aria-hidden>
          📊
        </div>
        <p className="mt-3 text-lg font-bold text-[#1a1f3a]">Раздел в разработке</p>
        <p className="mt-1 max-w-md text-sm leading-6 text-[#6b6f88]">
          Здесь появятся виджеты, метрики и аналитика отдела продаж: воронка, динамика, план-факт.
        </p>
      </div>
    </div>
  );
}
