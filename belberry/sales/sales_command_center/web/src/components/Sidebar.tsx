'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, CalendarDays, Radio, BellRing, LogOut } from 'lucide-react';

const NAV = [
  { href: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { href: '/daily', label: 'Дневной отчёт', Icon: CalendarDays },
  { href: '/alerts', label: 'Алерты', Icon: BellRing },
];

const SOON = [{ label: 'Сегодня', Icon: Radio, tag: 'live' }];

const ROLE_LABEL: Record<string, string> = {
  director: 'Руководитель',
  rop: 'РОП',
  manager: 'Менеджер',
};

function initials(value: string): string {
  const base = value.split('@')[0].replace(/[._-]+/g, ' ').trim();
  const parts = base.split(/\s+/).filter(Boolean);
  const chars = parts.length >= 2 ? parts[0][0] + parts[1][0] : base.slice(0, 2);
  return chars.toUpperCase();
}

export function Sidebar({ user }: { user?: { email?: string; role?: string } }) {
  const pathname = usePathname();
  const email = user?.email ?? '';
  const role = user?.role ? (ROLE_LABEL[user.role] ?? user.role) : '';

  return (
    <aside className="bb-rail">
      <div className="bb-rail-glow" aria-hidden />
      <div className="bb-brand">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/belberry-logo.svg" alt="Belberry" className="bb-brand-img" />
        <small className="bb-brand-tag">Командный центр</small>
      </div>

      <nav className="bb-nav">
        <div className="bb-nav-label">Обзор</div>
        {NAV.map(({ href, label, Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className={`bb-nav-item${active ? ' active' : ''}`}
            >
              <Icon size={18} strokeWidth={2} />
              {label}
            </Link>
          );
        })}
        <div className="bb-nav-label">Скоро</div>
        {SOON.map(({ label, Icon, tag }) => (
          <span key={label} className="bb-nav-item soon" aria-disabled>
            <Icon size={18} strokeWidth={2} />
            {label}
            <span className="bb-nav-tag">{tag}</span>
          </span>
        ))}
      </nav>

      <div className="bb-rail-foot">
        <div className="bb-ava">{email ? initials(email) : 'ОП'}</div>
        <div className="bb-who">
          <b>{email || 'Гость'}</b>
          {role ? <small>{role}</small> : null}
        </div>
        <form action="/api/auth/logout" method="post">
          <button className="bb-logout" aria-label="Выйти" title="Выйти">
            <LogOut size={17} strokeWidth={2} />
          </button>
        </form>
      </div>
    </aside>
  );
}
