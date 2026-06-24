'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { DealAudit } from '@/lib/audit';

const BAND_COLOR: Record<string, string> = { low: 'var(--bb-red)', mid: 'var(--bb-amber)', hi: 'var(--bb-green)' };
const BAND_BG: Record<string, string> = { low: '#fdeced', mid: '#fdf2e7', hi: '#e7f4ec' };

// Транслитерация кириллицы для slug в URL.
const TRANSLIT: Record<string, string> = {
  а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'zh',з:'z',и:'i',й:'y',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',
  р:'r',с:'s',т:'t',у:'u',ф:'f',х:'h',ц:'ts',ч:'ch',ш:'sh',щ:'sch',ъ:'',ы:'y',ь:'',э:'e',ю:'yu',я:'ya',
};
function slugify(s: string): string {
  return s.toLowerCase().split('').map((c) => TRANSLIT[c] ?? c).join('')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'deal';
}
// URL аудита: /audit/<id>-<название>-<дата>. id-префикс — для поиска, остальное для читаемости.
export function auditHref(a: { id: number; title: string | null; dealId: number; createdAt: Date | string | null }): string {
  const name = slugify(a.title ?? `deal-${a.dealId}`);
  const d = a.createdAt ? new Date(a.createdAt) : null;
  const date = d && !Number.isNaN(d.getTime())
    ? new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit' }).format(d)
    : '';
  return `/audit/${a.id}-${name}${date ? `-${date}` : ''}`;
}

function fmtDate(v: Date | string | null): string {
  if (!v) return '—';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' });
}

// Стили плашки «Итог» (мягкая заливка по смыслу).
const OUTCOME_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  current: { bg: '#e7f4ec', color: 'var(--bb-green)', label: '↩︎ Вернули текущему' },
  transferred: { bg: 'var(--bb-violet-soft)', color: 'var(--bb-violet)', label: '→ Передали другому' },
  telemarketing: { bg: '#fdf2e7', color: '#b5651d', label: '📞 В телемаркетинг' },
};

function OutcomeCell({ a }: { a: DealAudit }) {
  if (a.status === 'error') return <span style={{ color: 'var(--bb-faint)' }}>ошибка аудита</span>;
  if (a.status !== 'ready') return <span style={{ color: 'var(--bb-faint)' }}>⏳ выполняется…</span>;
  if (!a.returnedToWork) return <span style={{ color: 'var(--bb-faint)' }}>— не возвращена</span>;
  const s = a.outcomeKind ? OUTCOME_STYLE[a.outcomeKind] : null;
  if (!s) return <span style={{ color: 'var(--bb-green)', fontWeight: 600 }}>✓ в работе</span>;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: s.bg, color: s.color, borderRadius: 9, padding: '4px 9px', fontSize: 11.5, fontWeight: 600, whiteSpace: 'nowrap' }}>
      {s.label}
      {a.outcomeResponsibleName && <span style={{ fontWeight: 500, opacity: 0.85 }}>· {a.outcomeResponsibleName}</span>}
    </span>
  );
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
          <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
          <table className="bb-table" style={{ fontSize: 12.5, minWidth: 980 }}>
            <thead><tr><th>Сделка</th><th>Стадия при аудите</th><th>Заказал</th><th>Дата</th><th>Шанс</th><th>Менеджер на начало аудита</th><th>Новый менеджер</th><th>Итог</th><th></th></tr></thead>
            <tbody>
              {audits.map((a) => (
                <tr key={a.id} onClick={() => router.push(auditHref(a))} style={{ cursor: 'pointer' }}>
                  <td style={{ whiteSpace: 'nowrap' }}><b>{a.title ?? `Сделка #${a.dealId}`}</b></td>
                  <td style={{ color: 'var(--bb-muted)', whiteSpace: 'nowrap' }}>{a.stageLabel ?? '—'}</td>
                  <td style={{ color: 'var(--bb-muted)', whiteSpace: 'nowrap' }}>{a.requestedByName ?? '—'}</td>
                  <td style={{ color: 'var(--bb-muted)', whiteSpace: 'nowrap' }}>{fmtDate(a.createdAt)}</td>
                  <td>{a.status === 'ready'
                    ? <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '3px 10px', background: BAND_BG[a.band ?? 'low'], color: BAND_COLOR[a.band ?? 'low'] }}>{a.score}%</span>
                    : '—'}</td>
                  <td style={{ color: 'var(--bb-muted)', whiteSpace: 'nowrap' }}>{a.responsibleAtAuditName ?? '—'}</td>
                  <td style={{ whiteSpace: 'nowrap', fontWeight: a.outcomeResponsibleName && a.outcomeResponsibleName !== a.responsibleAtAuditName ? 600 : 400, color: a.outcomeResponsibleName && a.outcomeResponsibleName !== a.responsibleAtAuditName ? 'var(--bb-violet)' : 'var(--bb-muted)' }}>{a.returnedToWork ? (a.outcomeResponsibleName ?? '—') : '—'}</td>
                  <td><OutcomeCell a={a} /></td>
                  <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}><Link href={auditHref(a)} onClick={(e) => e.stopPropagation()} style={{ color: 'var(--bb-violet)', fontWeight: 600, textDecoration: 'none' }}>открыть →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
