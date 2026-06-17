'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { canSeeKp } from '@/lib/kp-access';
import { LayoutDashboard, CalendarDays, Radio, BellRing, LogOut, Search, ClipboardCheck, PhoneCall, FileText } from 'lucide-react';

const NAV = [
  { href: '/dashboard', label: 'Дашборд ОП', Icon: LayoutDashboard, tag: undefined },
  { href: '/telemarketing', label: 'Дашборд ТМ', Icon: PhoneCall, tag: undefined },
  { href: '/today', label: 'Сегодня', Icon: Radio, tag: 'live' },
  { href: '/daily', label: 'Дневной отчёт', Icon: CalendarDays, tag: undefined },
  { href: '/meetings', label: 'Анализ встреч', Icon: ClipboardCheck, tag: undefined },
  { href: '/kp', label: 'Сборка КП', Icon: FileText, tag: undefined },
  { href: '/alerts', label: 'Алерты', Icon: BellRing, tag: undefined },
];

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
  // пилот «Сборка КП»: пункт меню видят только пользователи из kp-access
  const nav = NAV.filter((item) => item.href !== '/kp' || canSeeKp(user?.email));
  const pathname = usePathname();
  const email = user?.email ?? '';
  const role = user?.role ? (ROLE_LABEL[user.role] ?? user.role) : '';
  const [alertCount, setAlertCount] = useState(0);

  useEffect(() => {
    let alive = true;
    fetch('/api/alerts/count')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d && typeof d.count === 'number') setAlertCount(d.count);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  return (
    <aside className="bb-rail">
      <div className="bb-rail-glow" aria-hidden />
      <div className="bb-brand">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/belberry-logo.svg" alt="Belberry" className="bb-brand-img" />
        <small className="bb-brand-tag">Командный центр</small>
      </div>

      <nav className="bb-nav">
        <button
          type="button"
          className="bb-nav-search"
          onClick={() => window.dispatchEvent(new CustomEvent('bb-cmdk-open'))}
        >
          <Search size={16} strokeWidth={2} />
          Поиск
          <kbd>⌘K</kbd>
        </button>
        <div className="bb-nav-label">Обзор</div>
        {nav.map(({ href, label, Icon, tag }) => {
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
              {href === '/alerts' && alertCount > 0 ? <span className="bb-nav-count">{alertCount}</span> : null}
              {tag ? <span className="bb-nav-tag">{tag}</span> : null}
            </Link>
          );
        })}
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
