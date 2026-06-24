'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { DealAudit } from '@/lib/audit';

const BAND_COLOR: Record<string, string> = { low: 'var(--bb-red)', mid: 'var(--bb-amber)', hi: 'var(--bb-green)' };
const BAND_BG: Record<string, string> = { low: '#fdeced', mid: '#fdf2e7', hi: '#e7f4ec' };

function fmtDate(v: Date | string | null): string {
  if (!v) return '—';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' });
}

export function AuditView({ initialAudits }: { initialAudits: DealAudit[] }) {
  const router = useRouter();
  const [audits, setAudits] = useState<DealAudit[]>(initialAudits);
  const [input, setInput] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/audit', { cache: 'no-store' });
      if (r.ok) setAudits((await r.json()).audits);
    } catch { /* сеть мигнула */ }
  }, []);

  // пока есть незавершённые — обновляем список
  useEffect(() => {
    if (!audits.some((a) => a.status === 'pending' || a.status === 'collecting')) return;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [audits, refresh]);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true);
    const r = await fetch('/api/audit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deal: input }),
    });
    setBusy(false);
    if (!r.ok) { setErr((await r.json().catch(() => null))?.error ?? `Ошибка ${r.status}`); return; }
    const { id } = await r.json();
    router.push(`/audit/${id}`); // переход на страницу отчёта (она сама опрашивает статус)
  }

  return (
    <div className="bb-page">
      <div className="bb-hero bb-aurora">
        <div className="bb-hero-eyebrow">АУДИТ СДЕЛОК</div>
        <div className="bb-hero-title">Разобрать сделку за минуту</div>
        <div className="bb-hero-sub">Вставь ссылку или ID — соберём встречи, транскрипты, переписку, звонки и КП, оценим честный шанс возврата и предложим следующий шаг.</div>
        <form onSubmit={submit} style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap', position: 'relative' }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="https://belberrycrm.bitrix24.ru/crm/deal/details/23332/ или 23332"
            style={{ flex: 1, minWidth: 260, border: '1px solid rgba(255,255,255,.25)', background: 'rgba(255,255,255,.12)', color: '#fff', borderRadius: 12, padding: '12px 15px', fontSize: 14 }} />
          <button type="submit" disabled={busy} style={{ background: '#fff', color: 'var(--bb-indigo)', border: 0, borderRadius: 12, padding: '12px 22px', fontWeight: 700, cursor: 'pointer' }}>
            {busy ? 'Запускаю…' : 'Запустить аудит →'}
          </button>
        </form>
        {err && <div style={{ color: '#ffd2d2', fontSize: 13, marginTop: 8, position: 'relative' }}>{err}</div>}
      </div>

      <div className="bb-card">
        <div className="bb-sect-head"><div className="bb-sect-ic">📁</div><h2>Недавние аудиты</h2></div>
        {audits.length === 0 ? (
          <div style={{ color: 'var(--bb-faint)', fontSize: 13 }}>Пока пусто — запусти первый аудит.</div>
        ) : (
          <table className="bb-table">
            <thead><tr><th>Сделка</th><th>Стадия при аудите</th><th>Заказал</th><th>Дата</th><th>Шанс</th><th>Статус</th><th></th></tr></thead>
            <tbody>
              {audits.map((a) => (
                <tr key={a.id} onClick={() => router.push(`/audit/${a.id}`)} style={{ cursor: 'pointer' }}>
                  <td><b>{a.title ?? `Сделка #${a.dealId}`}</b> <span style={{ color: 'var(--bb-faint)' }}>#{a.dealId}</span></td>
                  <td style={{ color: 'var(--bb-muted)' }}>{a.stageLabel ?? '—'}</td>
                  <td style={{ color: 'var(--bb-muted)' }}>{a.requestedByName ?? '—'}</td>
                  <td style={{ color: 'var(--bb-muted)', whiteSpace: 'nowrap' }}>{fmtDate(a.createdAt)}</td>
                  <td>{a.status === 'ready'
                    ? <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '3px 10px', background: BAND_BG[a.band ?? 'low'], color: BAND_COLOR[a.band ?? 'low'] }}>{a.score}%</span>
                    : '—'}</td>
                  <td style={{ color: 'var(--bb-muted)' }}>{a.status === 'ready' ? (a.returnedToWork ? '✓ в работе' : 'готов') : a.status === 'error' ? 'ошибка' : '⏳ …'}</td>
                  <td><Link href={`/audit/${a.id}`} onClick={(e) => e.stopPropagation()} style={{ color: 'var(--bb-violet)', fontWeight: 600, textDecoration: 'none' }}>открыть →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
