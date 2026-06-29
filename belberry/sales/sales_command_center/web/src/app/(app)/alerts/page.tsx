import { redirect } from 'next/navigation';

// Голый /alerts → дефолтная вкладка «Сделки».
export default function AlertsPage() {
  redirect('/alerts/deals');
}
