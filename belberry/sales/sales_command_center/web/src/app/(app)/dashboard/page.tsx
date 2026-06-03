export default function DashboardPage() {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-12 px-10 py-14">
      <header className="space-y-1.5">
        <p className="text-sm font-medium text-[#6e6e73]">Платформа</p>
        <h1 className="text-[2.1rem] font-semibold leading-tight tracking-[-0.022em] text-[#1d1d1f]">
          Dashboard
        </h1>
      </header>

      <div className="flex min-h-[360px] flex-col items-center justify-center rounded-3xl border border-[#e8e8ed] bg-white px-6 text-center shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        <div className="text-5xl" aria-hidden>
          📊
        </div>
        <p className="mt-4 text-lg font-semibold tracking-[-0.018em] text-[#1d1d1f]">
          Раздел в разработке
        </p>
        <p className="mt-1.5 max-w-md text-[0.95rem] leading-relaxed text-[#6e6e73]">
          Здесь появятся виджеты, метрики и аналитика отдела продаж: воронка, динамика, план-факт.
        </p>
      </div>
    </div>
  );
}
