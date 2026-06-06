import { getIronSession } from 'iron-session';
import { NextRequest, NextResponse } from 'next/server';
import { isPreviewMode } from './lib/preview';
import { sessionOptions, type SessionData } from './lib/session';

const NOINDEX = 'noindex, nofollow';

function isPublicPath(pathname: string): boolean {
  return (
    pathname === '/login' ||
    pathname === '/api/auth' ||
    pathname.startsWith('/api/auth/') ||
    pathname.startsWith('/_next/') ||
    pathname === '/favicon.ico' ||
    pathname === '/favicon.svg' ||
    pathname === '/belberry-logo.svg' ||
    pathname === '/robots.txt'
  );
}

function withNoindex(response: NextResponse): NextResponse {
  response.headers.set('X-Robots-Tag', NOINDEX);
  return response;
}

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;

  if (isPublicPath(pathname)) {
    return withNoindex(NextResponse.next());
  }

  // Локальный preview: пускаем без сессии (только вне прода, см. isPreviewMode).
  if (isPreviewMode()) {
    return withNoindex(NextResponse.next());
  }

  const response = NextResponse.next();
  const session = await getIronSession<SessionData>(request, response, sessionOptions);

  if (!session.bitrixId) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set(
      'redirect',
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    );

    return withNoindex(NextResponse.redirect(loginUrl));
  }

  return withNoindex(response);
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|robots.txt).*)'],
};
