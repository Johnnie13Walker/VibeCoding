export function isSafeModeEnabled() {
  return String(process.env.SAFE_MODE || '1').trim() === '1';
}

export function assertMutableActionAllowed(actionName) {
  if (!isSafeModeEnabled()) return;
  const blocked = new Set(['bitrix_create', 'external_create', 'external_mutation']);
  if (blocked.has(actionName)) {
    throw new Error(`SAFE_MODE blocks action: ${actionName}`);
  }
}
