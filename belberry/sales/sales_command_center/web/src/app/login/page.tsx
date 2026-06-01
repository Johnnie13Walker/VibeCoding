import { redirect } from 'next/navigation';
import { requireSession } from '@/lib/auth';
import { LoginForm } from './LoginForm';

interface LoginPageProps {
  searchParams: Promise<{
    redirect?: string;
  }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const session = await requireSession();
  const params = await searchParams;
  const redirectTo = params.redirect?.startsWith('/') ? params.redirect : '/';

  if (session) {
    redirect(redirectTo);
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <LoginForm redirectTo={redirectTo} />
    </main>
  );
}
