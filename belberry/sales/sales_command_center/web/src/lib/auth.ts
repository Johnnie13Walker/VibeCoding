import { isPreviewMode } from './preview';
import { getSession } from './session';

export async function requireSession() {
  const session = await getSession();

  // В preview-режиме (только локально) пускаем без логина.
  if (!session.bitrixId && !isPreviewMode()) {
    return null;
  }

  return session;
}
