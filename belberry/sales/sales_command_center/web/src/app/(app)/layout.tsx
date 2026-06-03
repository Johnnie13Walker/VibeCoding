import { redirect } from 'next/navigation';
import { Sidebar } from '@/components/Sidebar';
import { requireSession } from '@/lib/auth';

export default async function PlatformLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();

  if (!session) {
    redirect('/login');
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
