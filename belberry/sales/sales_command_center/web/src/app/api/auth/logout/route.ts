import { NextResponse } from 'next/server';
import { getSession } from '@/lib/session';

export const runtime = 'nodejs';

export async function POST() {
  const session = await getSession();
  session.destroy();

  // Кнопка «Выйти» — обычная form-навигация, поэтому возвращаем редирект
  // на /login (303 → браузер делает GET), а не JSON (иначе на экране
  // показывался голый {"ok":true}). Относительный Location — чтобы за
  // nginx-прокси не уехать на внутренний 127.0.0.1:3010. Очистка cookie
  // сессии (next/headers cookies) применяется к этому ответу автоматически.
  return new NextResponse(null, {
    status: 303,
    headers: { Location: '/login' },
  });
}
