import { getIronSession, type SessionOptions } from 'iron-session';
import { cookies } from 'next/headers';

export type UserRole = 'director' | 'rop' | 'manager';

export interface SessionData {
  bitrixId?: number;
  email?: string;
  role?: UserRole;
}

export const sessionOptions: SessionOptions = {
  password: process.env.SESSION_SECRET!,
  cookieName: 'scc_session',
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    // Вход живёт рабочий день: деактивированный в Bitrix сотрудник теряет
    // доступ в течение суток, менеджер раз в день вводит код (он и так
    // приходит утром вместе со ссылкой на отчёт).
    maxAge: 60 * 60 * 12,
  },
};

export async function getSession() {
  return getIronSession<SessionData>(await cookies(), sessionOptions);
}
