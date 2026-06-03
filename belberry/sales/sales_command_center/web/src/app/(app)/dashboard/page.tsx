import { FunnelChart } from '@/components/dashboard/FunnelChart';
import { getDashboardData } from '@/lib/dashboard';

export const dynamic = 'force-dynamic';

function rub(n: number): string {
  return `${new Intl.NumberFormat('ru-RU').format(Math.round(n))} ₽`;
}

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-[#e8e8ed] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <p className="text-[0.8rem] font-medium text-[#6e6e73]">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tracking-[-0.02em] text-[#1d1d1f]">{value}</p>
      {hint ? <p className="mt-0.5 text-[0.8rem] text-[#86868b]">{hint}</p> : null}
    </div>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl border border-[#e8e8ed] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <div className="mb-5">
        <h2 className="text-lg font-semibold tracking-[-0.018em] text-[#1d1d1f]">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-[0.85rem] text-[#6e6e73]">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

export default async function DashboardPage() {
  const data = await getDashboardData();

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 px-10 py-14">
      <header className="space-y-1.5">
        <p className="text-sm font-medium text-[#6e6e73]">Платформа · {data.monthLabel}</p>
        <h1 className="text-[2.1rem] font-semibold leading-tight tracking-[-0.022em] text-[#1d1d1f]">
          Dashboard
        </h1>
      </header>

      {/* Сводные показатели */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Сделок в воронке" value={String(data.funnelCount)} hint="открытые, воронка Продажи" />
        <StatCard label="Сумма воронки" value={rub(data.funnelAmount)} hint="потенциал открытых сделок" />
        <StatCard label="Встреч за месяц" value={String(data.meetingsHeldTotal)} hint="проведено отделом" />
      </div>

      {/* Воронка */}
      <Card title="Воронка продаж" subtitle={`Открытые сделки по стадиям · снимок ${data.snapshotDate ?? '—'}`}>
        <FunnelChart data={data.funnel} />

        {data.stuck.length > 0 ? (
          <div className="mt-6 border-t border-[#f0f0f3] pt-5">
            <h3 className="text-[0.95rem] font-semibold text-[#1d1d1f]">Застрявшие сделки</h3>
            <p className="mb-3 mt-0.5 text-[0.8rem] text-[#86868b]">Дольше всего без движения — под риском.</p>
            <ul className="divide-y divide-[#f0f0f3]">
              {data.stuck.map((d) => (
                <li key={d.dealId} className="flex items-center justify-between gap-4 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-[0.92rem] font-medium text-[#1d1d1f]">{d.title}</p>
                    <p className="text-[0.78rem] text-[#86868b]">
                      {d.stageLabel} · {d.manager}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-[0.92rem] font-semibold text-[#1d1d1f]">{rub(d.amount)}</p>
                    <p className="text-[0.78rem] text-[#d4202e]">{d.stuckDays} дн. без движения</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Card>

      {/* Команда */}
      <Card title="Команда" subtitle={`Активность за ${data.monthLabel} · план встреч ${data.meetingsPlan}/чел`}>
        {data.team.length === 0 ? (
          <p className="text-[0.95rem] text-[#6e6e73]">Нет данных активности за период.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[0.9rem]">
              <thead>
                <tr className="border-b border-[#e8e8ed] text-[0.78rem] font-medium uppercase tracking-wide text-[#86868b]">
                  <th className="py-2.5 pr-3 font-medium">Менеджер</th>
                  <th className="px-3 py-2.5 text-right font-medium">Встречи</th>
                  <th className="px-3 py-2.5 text-right font-medium">Наборы</th>
                  <th className="px-3 py-2.5 text-right font-medium">Звонки 120с+</th>
                  <th className="px-3 py-2.5 text-right font-medium">КП</th>
                  <th className="px-3 py-2.5 text-right font-medium">Сделок</th>
                  <th className="py-2.5 pl-3 text-right font-medium">Часы</th>
                </tr>
              </thead>
              <tbody>
                {data.team.map((m) => (
                  <tr key={m.managerId} className="border-b border-[#f0f0f3] last:border-0">
                    <td className="py-2.5 pr-3 font-medium text-[#1d1d1f]">{m.name}</td>
                    <td className="px-3 py-2.5 text-right">
                      <span
                        className={
                          m.meetingsHeld >= data.meetingsPlan
                            ? 'font-semibold text-[#2c7a4a]'
                            : 'text-[#1d1d1f]'
                        }
                      >
                        {m.meetingsHeld}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-[#3a3f5c]">{m.dials}</td>
                    <td className="px-3 py-2.5 text-right text-[#3a3f5c]">{m.calls120}</td>
                    <td className="px-3 py-2.5 text-right text-[#3a3f5c]">{m.kpSent}</td>
                    <td className="px-3 py-2.5 text-right text-[#3a3f5c]">{m.dealsCreated}</td>
                    <td className="py-2.5 pl-3 text-right text-[#3a3f5c]">{m.talkHours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Что в разработке */}
      <Card title="Скоро" subtitle="Требуют дополнительного сбора данных из Bitrix">
        <ul className="space-y-1.5 text-[0.92rem] text-[#6e6e73]">
          <li>💰 План-факт оплат и прогноз закрытия месяца (нужен сбор WON-сделок)</li>
          <li>📦 Структура по продуктам и регулярка vs разовое / MRR (нужен сбор productrow)</li>
          <li>⭐ Качество встреч по баллам разбора</li>
        </ul>
      </Card>
    </div>
  );
}
