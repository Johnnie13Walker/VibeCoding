import { getSession } from './session';

export async function requireSession() {
  const session = await getSession();

  if (!session.bitrixId) {
    return null;
  }

  return session;
}
