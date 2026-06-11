'use client';

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, FileText, Loader2, Sparkles } from 'lucide-react';
import type { KpJob } from '@/lib/kp';

const PORTAL = 'https://belberrycrm.bitrix24.ru';
const dealUrl = (id: number) => `${PORTAL}/crm/deal/details/${id}/`;

const STATUS_LABEL: Record<string, string> = {
  pending: 'в очереди',
  collecting: 'собираем…',
  ready: 'готово',
  error: 'ошибка',
};
const STATUS_COLOR: Record<string, string> = {
  pending: '#9a9aa0',
  collecting: '#5b50d6',
  ready: '#2c7a4a',
  error: '#d4202e',
};

function fmtTime(v: Date | string | null): string {
  if (!v) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      timeZone: 'Europe/Moscow',
    }).format(new Date(v));
  } catch {
    return String(v);
  }
}

function JobDetails({ job }: { job: KpJob }) {
  const d = job.kpData;
  if (job.status === 'error') {
    return <p style={{ fontSize: 13, color: '#d4202e', marginTop: 8 }}>{job.error ?? 'без описания'}</p>;
  }
  if (!d) return null;
  return (
    <div style={{ marginTop: 10, display: 'grid', gap: 12 }}>
      <div>
        <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--bb-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Факты (каждый — с источником)
        </p>
        <ul style={{ listStyle: 'none', marginTop: 6, display: 'grid', gap: 3 }}>
          {d.facts.map((f) => (
            <li key={f.key} style={{ fontSize: 13, display: 'flex', gap: 8 }}>
              <span style={{ color: 'var(--bb-muted)', flex: '0 0 auto' }}>{f.key}:</span>
              <span style={{ fontWeight: 600, minWidth: 0 }}>{String(f.value)}</span>
              <span style={{ color: 'var(--bb-faint)', fontSize: 11.5, marginLeft: 'auto', flex: '0 0 auto' }}>{f.source}</span>
            </li>
          ))}
        </ul>
      </div>
      {d.hypotheses.length > 0 && (
        <div>
          <p style={{ fontSize: 12, fontWeight: 700, color: '#b5651d', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Гипотезы — не факты</p>
          <ul style={{ listStyle: 'none', marginTop: 6 }}>
            {d.hypotheses.map((h) => (
              <li key={h.key} style={{ fontSize: 13, color: 'var(--bb-muted)' }}>⚠ {h.note}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--bb-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Чек-лист сейлсу</p>
        <ul style={{ marginTop: 6, paddingLeft: 18 }}>
          {d.manual_checklist.map((m) => (
            <li key={m} style={{ fontSize: 13, margin: '2px 0' }}>{m}</li>
          ))}
        </ul>
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <a
          href={`/api/kp/${job.id}/deck`}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, borderRadius: 10,
            padding: '9px 16px', fontSize: 13.5, fontWeight: 700, textDecoration: 'none',
            background: 'var(--bb-violet)', color: '#fff',
          }}
        >
          <FileText size={15} /> Черновик деки
        </a>
        <a
          href={`/api/kp/${job.id}/smeta`}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, borderRadius: 10,
            padding: '9px 16px', fontSize: 13.5, fontWeight: 700, textDecoration: 'none',
            background: '#2c7a4a', color: '#fff',
          }}
        >
          <FileText size={15} /> Смета (xlsx)
        </a>
        <span style={{ fontSize: 11.5, color: '#b5651d', fontWeight: 600 }}>
          смета — тарифы матрицы, состав подтвердить со сметчиком; цены в деке заменить из сметы
        </span>
      </div>
      <p style={{ fontSize: 11.5, color: 'var(--bb-faint)' }}>
        Печать в PDF — из открывшейся деки (Cmd/Ctrl+P). Смета — kp_smeta.py по матрице.
      </p>
    </div>
  );
}

export function KpView({ initialJobs }: { initialJobs: KpJob[] }) {
  const [jobs, setJobs] = useState<KpJob[]>(initialJobs);
  const [dealId, setDealId] = useState('');
  const [brand, setBrand] = useState<'belberry' | 'acoola'>('belberry');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/kp', { cache: 'no-store' });
      if (r.ok) setJobs((await r.json()).jobs);
    } catch {
      /* сеть мигнула — обновимся следующим тиком */
    }
  }, []);

  // пока есть незавершённые задания — опрашиваем каждые 5 секунд
  useEffect(() => {
    if (!jobs.some((j) => j.status === 'pending' || j.status === 'collecting')) return;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [jobs, refresh]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const id = Number(dealId);
    if (!Number.isInteger(id) || id <= 0) {
      setErr('ID сделки — целое число, например 18484');
      return;
    }
    setBusy(true);
    try {
      const r = await fetch('/api/kp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dealId: id, brand }),
      });
      if (!r.ok) {
        setErr((await r.json().catch(() => null))?.error ?? `Ошибка ${r.status}`);
      } else {
        setDealId('');
        await refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #2b2a5e, #5b50d6)' }}>
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">КП-движок · фактура по сделке за ~1 минуту</div>
            <h1 className="bb-hero-title">Сборка КП</h1>
            <div className="bb-hero-sub">сделка → бриф и транскрипты → SEO-аудит → факты с источниками → чек-лист</div>
          </div>
          <FileText size={40} color="#fff" style={{ opacity: 0.9 }} />
        </div>
      </div>

      <div className="bb-card" style={{ marginBottom: 16 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic"><Sparkles size={17} /></span>
          <h2>Новое задание</h2>
          <small>аудит PR-CY + бриф + Метрика (если доступна)</small>
        </div>
        <form onSubmit={submit} style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            value={dealId}
            onChange={(e) => setDealId(e.target.value)}
            placeholder="ID сделки, напр. 18484"
            inputMode="numeric"
            style={{ border: '1px solid var(--bb-line)', borderRadius: 10, padding: '9px 14px', fontSize: 14, width: 200 }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            {(['belberry', 'acoola'] as const).map((b) => (
              <button
                key={b}
                type="button"
                onClick={() => setBrand(b)}
                style={{
                  borderRadius: 999, padding: '7px 14px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                  border: `1px solid ${brand === b ? 'transparent' : 'var(--bb-line)'}`,
                  background: brand === b ? (b === 'acoola' ? '#3086FB' : 'var(--bb-violet)') : '#fff',
                  color: brand === b ? '#fff' : 'var(--bb-muted)',
                }}
              >
                {b === 'belberry' ? 'Belberry · медицина' : 'Acoola Team'}
              </button>
            ))}
          </div>
          <button
            type="submit"
            disabled={busy}
            style={{
              borderRadius: 10, padding: '9px 18px', fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
              border: 'none', background: 'var(--bb-violet)', color: '#fff', opacity: busy ? 0.6 : 1,
            }}
          >
            {busy ? 'Создаём…' : '⚙ Собрать фактуру'}
          </button>
          {err && <span style={{ fontSize: 13, color: '#d4202e' }}>{err}</span>}
        </form>
      </div>

      <div className="bb-card">
        <div className="bb-sect-head">
          <span className="bb-sect-ic"><FileText size={17} /></span>
          <h2>Задания</h2>
          <small>{jobs.length}</small>
        </div>
        {jobs.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Заданий пока нет — создай первое сверху.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {jobs.map((j) => (
              <li key={j.id} style={{ padding: '11px 0', borderBottom: '1px solid var(--bb-line)' }}>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}
                  onClick={() => setOpen(open === j.id ? null : j.id)}
                >
                  {j.status === 'collecting'
                    ? <Loader2 size={14} className="animate-spin" style={{ color: STATUS_COLOR.collecting, flex: '0 0 auto' }} />
                    : <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATUS_COLOR[j.status] ?? '#9a9aa0', flex: '0 0 auto' }} />}
                  <a
                    href={dealUrl(j.dealId)}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    style={{ fontWeight: 600, fontSize: 14, color: 'var(--bb-ink)', textDecoration: 'none', display: 'inline-flex', gap: 5, alignItems: 'center' }}
                  >
                    {j.kpData?.domain || `сделка #${j.dealId}`} <ExternalLink size={12} style={{ opacity: 0.5 }} />
                  </a>
                  <span style={{
                    fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '3px 9px',
                    background: j.brand === 'acoola' ? '#eaf2fe' : 'var(--bb-violet-soft)',
                    color: j.brand === 'acoola' ? '#3086FB' : 'var(--bb-violet)',
                  }}>
                    {j.brand === 'acoola' ? 'Acoola' : 'Belberry'}
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, color: STATUS_COLOR[j.status] ?? 'var(--bb-muted)' }}>
                    {STATUS_LABEL[j.status] ?? j.status}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--bb-faint)' }}>{fmtTime(j.createdAt)}</span>
                </div>
                {open === j.id && <JobDetails job={j} />}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
