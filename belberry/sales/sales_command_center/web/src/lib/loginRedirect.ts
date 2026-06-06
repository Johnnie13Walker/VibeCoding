export function safeLoginRedirect(value: string | undefined): string {
  if (!value?.startsWith('/') || value.startsWith('//')) {
    return '/';
  }

  if (value === '/login' || value.startsWith('/login?') || value.startsWith('/api/')) {
    return '/';
  }

  return value;
}
