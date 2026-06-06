import { getMeetingsForAnalysis } from '@/lib/meetings';
import { MeetingsView } from '@/components/meetings/MeetingsView';

export const dynamic = 'force-dynamic';

export default async function MeetingsPage() {
  const items = await getMeetingsForAnalysis();
  return <MeetingsView items={items} />;
}
