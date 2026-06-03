'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV = [
  { href: '/dashboard', label: 'Dashboard', icon: '📊' },
  { href: '/daily', label: 'Дневной отчет ОП', icon: '📅' },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-[#e8e4f2] bg-white">
      <div className="flex items-center gap-2 border-b border-[#e8e4f2] px-5 py-5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/belberry-logo.svg" alt="Belberry" className="h-7 w-auto" />
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? 'page' : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                active
                  ? 'bg-[#ece9f9] text-[#4a3fc5]'
                  : 'text-[#4b4f66] hover:bg-[#f3effc] hover:text-[#4a3fc5]'
              }`}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <form action="/api/auth/logout" method="post" className="border-t border-[#e8e4f2] p-3">
        <button className="w-full rounded-lg border border-[#cfc8f3] bg-white px-3 py-2 text-sm font-semibold text-[#5b50d6] transition hover:bg-[#f3effc]">
          Выйти
        </button>
      </form>
    </aside>
  );
}
