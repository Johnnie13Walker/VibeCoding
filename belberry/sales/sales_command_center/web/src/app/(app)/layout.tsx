import { redirect } from 'next/navigation';
import { Sidebar } from '@/components/Sidebar';
import { CommandPalette } from '@/components/CommandPalette';
import { requireSession } from '@/lib/auth';

export default async function PlatformLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();

  if (!session) {
    redirect('/login');
  }

  return (
    <div className="flex min-h-screen max-md:flex-col">
      <Sidebar user={{ email: session.email, role: session.role }} />
      <main className="min-w-0 flex-1">{children}</main>
      <CommandPalette />
    </div>
  );
}
