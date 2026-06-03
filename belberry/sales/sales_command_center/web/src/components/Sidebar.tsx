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
    <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-[#e8e8ed] bg-white/70 backdrop-blur-xl">
      <div className="flex h-16 items-center px-6">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/belberry-logo.svg" alt="Belberry" className="h-7 w-auto" />
      </div>

      <nav className="flex-1 space-y-0.5 px-3 pt-2">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? 'page' : undefined}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.95rem] tracking-[-0.01em] transition ${
                active
                  ? 'bg-[#f0eefb] font-semibold text-[#5b50d6]'
                  : 'font-medium text-[#1d1d1f] hover:bg-[#f5f5f7]'
              }`}
            >
              <span className="text-base" aria-hidden>
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <form action="/api/auth/logout" method="post" className="p-3">
        <button className="w-full rounded-xl px-3 py-2.5 text-left text-[0.95rem] font-medium text-[#6e6e73] transition hover:bg-[#f5f5f7] hover:text-[#1d1d1f]">
          Выйти
        </button>
      </form>
    </aside>
  );
}
