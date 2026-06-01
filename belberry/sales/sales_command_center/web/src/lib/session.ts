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
  },
};

export async function getSession() {
  return getIronSession<SessionData>(await cookies(), sessionOptions);
}
