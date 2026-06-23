'use client';

import { useCallback, useEffect, useState } from 'react';
import type { AuditResult, DealAudit } from '@/lib/audit';

const STAGES: { id: string; label: string }[] = [
  { id: 'C10:NEW', label: 'Квалификация' },
  { id: 'C10:PREPAYMENT_INVOIC', label: 'Подготовка БРИФа' },
  { id: 'C10:EXECUTING', label: 'Подготовка КП' },
  { id: 'C10:UC_4SJOE4', label: 'Защита КП' },
  { id: 'C10:FINAL_INVOICE', label: 'Получить решение' },
];

const BAND_LABEL: Record<string, string> = { low: 'низкий', mid: 'средний', hi: 'высокий' };
const BAND_COLOR: Record<string, string> = { low: 'var(--bb-red)', mid: 'var(--bb-amber)', hi: 'var(--bb-green)' };

function money(n?: number | null): string {
  return n ? `${n.toLocaleString('ru-RU')} ₽` : '—';
}

function tomorrow18iso(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.toISOString().slice(0, 10)}T18:00:00+03:00`;
}

function Gauge({ score, band }: { score: number; band: string }) {
  const r = 78;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - score / 100);
  return (
    <div style={{ position: 'relative', width: 180, height: 180 }}>
      <svg width="180" height="180" viewBox="0 0 180 180" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="90" cy="90" r={r} fill="none" stroke="#f0ece7" strokeWidth="16" />
        <circle cx="90" cy="90" r={r} fill="none" stroke={BAND_COLOR[band] ?? 'var(--bb-amber)'}
          strokeWidth="16" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
        <div>
          <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1, color: BAND_COLOR[band] }}>{score}%</div>
          <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 4 }}>шанс возврата</div>
        </div>
      </div>
    </div>
  );
}

function AuditDetail({ audit, onReturned }: { audit: DealAudit; onReturned: () => void }) {
  const r = audit.result as AuditResult | null;
  const n = r?.narrative ?? {};
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const chain = (r?.signals?.responsibles_chain as string[] | undefined) ?? [];
  const [stageId, setStageId] = useState('C10:EXECUTING');
  const [responsibleId, setResponsibleId] = useState(chain.length ? String(chain[chain.length - 1]) : '');
  const [deadline] = useState(tomorrow18iso());
  const [taskTitle, setTaskTitle] = useState(n.first_task?.title ?? 'Связаться по сделке');
  const [taskDesc, setTaskDesc] = useState(n.first_task?.description ?? '');

  if (audit.status === 'error') return <div className="bb-card"><b>Ошибка аудита:</b> {audit.error}</div>;
  if (audit.status !== 'ready' || !r)
    return <div className="bb-card bb-fade">⏳ Аудит выполняется (сбор данных + расшифровки + разбор)…</div>;

  async function returnToWork() {
    setBusy(true); setErr(null);
    const res = await fetch(`/api/audit/${audit.id}/return-to-work`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stageId, responsibleId: Number(responsibleId), deadline, taskTitle, taskDescription: taskDesc }),
    });
    setBusy(false);
    if (!res.ok) { setErr((await res.json().catch(() => null))?.error ?? `Ошибка ${res.status}`); return; }
    onReturned();
  }

  const rec = r.recovery;
  return (
    <div className="bb-fade">
      <div className="bb-card">
        <div className="bb-sect-head">
          <div className="bb-sect-ic">🔎</div>
          <h2>{r.title ?? `Сделка #${audit.dealId}`} <span className="bb-faint">#{audit.dealId}</span></h2>
          <small>{r.company} · <a className="bb-link" target="_blank" rel="noreferrer"
            href={`https://belberrycrm.bitrix24.ru/crm/deal/details/${audit.dealId}/`}>открыть в Bitrix ↗</a></small>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 24, alignItems: 'center' }}>
          <Gauge score={rec.score} band={rec.band} />
          <div>
            <span style={{ display: 'inline-block', fontWeight: 800, borderRadius: 999, padding: '5px 14px', marginBottom: 10,
              background: rec.band === 'hi' ? '#e7f4ec' : rec.band === 'mid' ? '#fdf2e7' : '#fdeced',
              color: BAND_COLOR[rec.band] }}>
              {(n.verdict_band_text ?? BAND_LABEL[rec.band] ?? '').toUpperCase()} · EV {money(rec.expected_value)}
            </span>
            <div style={{ fontSize: 15, lineHeight: 1.55 }}>{n.summary}</div>
            {n.real_cause && <div style={{ marginTop: 8, fontSize: 13.5, color: 'var(--bb-muted)' }}><b>Реальная причина:</b> {n.real_cause}</div>}
            <ul style={{ listStyle: 'none', padding: 0, marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 18px' }}>
              {rec.factors.map((f, i) => (
                <li key={i} style={{ fontSize: 13 }}>
                  <span style={{ color: f.weight > 0 ? 'var(--bb-green)' : 'var(--bb-red)', fontWeight: 700 }}>
                    {f.weight > 0 ? '＋' : '－'}</span> {f.label}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {!!n.chronology?.length && (
        <Section icon="🕑" title="Хронология">
          {n.chronology.map((e, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--bb-line)', fontSize: 13.5 }}>
              <span style={{ color: 'var(--bb-faint)', fontWeight: 600 }}>{e.date}</span>
              <span>{e.event} {e.who && <i style={{ color: 'var(--bb-faint)' }}>— {e.who}</i>}</span>
            </div>
          ))}
        </Section>
      )}

      {!!n.call_analysis?.length && (
        <Section icon="☎" title="Анализ звонков" hint={`записей: ${audit.result?.call_recordings?.length ?? 0}`}>
          {n.call_analysis.map((c, i) => (
            <div key={i} style={{ padding: '10px 0', borderBottom: '1px solid var(--bb-line)' }}>
              <b style={{ fontSize: 13.5 }}>☎ {c.date}: {c.summary}</b>
              <div style={{ fontSize: 12.5, color: 'var(--bb-muted)', marginTop: 4 }}>
                {c.client_tone && <div>Тон клиента: {c.client_tone}</div>}
                {!!c.objections?.length && <div>Возражения: {c.objections.join('; ')}</div>}
                {c.manager_quality && <div>Менеджер: {c.manager_quality}</div>}
                {c.commitment && <div>Обязательство: {c.commitment}</div>}
              </div>
            </div>
          ))}
        </Section>
      )}

      {!!n.failures?.length && (
        <Section icon="⚠️" title="Системные провалы">
          {n.failures.map((f, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--bb-line)' }}>
              <span style={{ flex: '0 0 auto', fontSize: 10.5, fontWeight: 700, background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)', borderRadius: 6, padding: '2px 7px', height: 'fit-content' }}>
                {f.pattern_id}{f.severity ? `/${f.severity}` : ''}</span>
              <div style={{ fontSize: 13.5 }}><b>{f.title}</b> — <span style={{ color: 'var(--bb-muted)' }}>{f.detail}</span></div>
            </div>
          ))}
        </Section>
      )}

      {!!n.what_would_save_it?.length && (
        <Section icon="⤷" title="Что спасло бы сделку">
          {n.what_would_save_it.map((w, i) => <li key={i} style={{ fontSize: 13.5, marginBottom: 6 }}>{w}</li>)}
        </Section>
      )}

      {!!n.next_steps?.length && (
        <Section icon="🎯" title="Следующие шаги">
          <ol style={{ paddingLeft: 18 }}>{n.next_steps.map((s, i) => <li key={i} style={{ fontSize: 13.5, marginBottom: 5 }}>{s}</li>)}</ol>
        </Section>
      )}

      {!!n.systemic_conclusions?.length && (
        <Section icon="🛠" title="Системные выводы (сломано → лечить)">
          {n.systemic_conclusions.map((c, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--bb-line)', fontSize: 13 }}>
              <b>{c.broken}</b> <span style={{ color: 'var(--bb-violet)' }}>→ {c.fix}</span>
            </div>
          ))}
        </Section>
      )}

      {/* Действие: вернуть в работу */}
      <div className="bb-card">
        <div className="bb-sect-head"><div className="bb-sect-ic">⚡</div><h2>Действия</h2></div>
        {audit.returnedToWork ? (
          <div style={{ color: 'var(--bb-green)', fontWeight: 600 }}>
            ✓ Сделка возвращена в работу{audit.taskId ? `, задача #${audit.taskId} поставлена` : ''}.
          </div>
        ) : !open ? (
          <button className="bb-btn-primary" onClick={() => setOpen(true)}
            style={{ background: 'var(--bb-violet)', color: '#fff', border: 0, borderRadius: 12, padding: '12px 18px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>
            ↩︎ Вернуть в работу + поставить задачу
          </button>
        ) : (
          <div style={{ border: '1px dashed #d9d3f7', borderRadius: 14, padding: 16, background: '#fbfaff' }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10, fontSize: 13 }}>
              <label>Стадия:{' '}
                <select value={stageId} onChange={(e) => setStageId(e.target.value)}>
                  {STAGES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
              </label>
              <label>Ответственный (Bitrix ID):{' '}
                <input value={responsibleId} onChange={(e) => setResponsibleId(e.target.value)}
                  style={{ width: 90, border: '1px solid var(--bb-line)', borderRadius: 8, padding: '4px 8px' }} />
              </label>
              <span style={{ color: 'var(--bb-muted)' }}>дедлайн: завтра 18:00</span>
            </div>
            <input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)}
              style={{ width: '100%', border: '1px solid var(--bb-line)', borderRadius: 8, padding: '8px 10px', marginBottom: 8, fontSize: 13.5 }} />
            <textarea value={taskDesc} onChange={(e) => setTaskDesc(e.target.value)}
              style={{ width: '100%', minHeight: 120, border: '1px solid var(--bb-line)', borderRadius: 8, padding: 10, fontSize: 13, resize: 'vertical' }} />
            {err && <div style={{ color: 'var(--bb-red)', fontSize: 13, marginTop: 8 }}>{err}</div>}
            <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
              <button disabled={busy} onClick={returnToWork}
                style={{ background: 'var(--bb-violet)', color: '#fff', border: 0, borderRadius: 12, padding: '10px 16px', fontWeight: 700, cursor: 'pointer' }}>
                {busy ? 'Возвращаю…' : 'Подтвердить — вернуть и поставить задачу'}
              </button>
              <button onClick={() => setOpen(false)} style={{ background: 'transparent', border: 0, color: 'var(--bb-muted)', cursor: 'pointer' }}>Отмена</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ icon, title, hint, children }: { icon: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="bb-card">
      <div className="bb-sect-head"><div className="bb-sect-ic">{icon}</div><h2>{title}</h2>{hint && <small>{hint}</small>}</div>
      {children}
    </div>
  );
}

export function AuditView({ initialAudits }: { initialAudits: DealAudit[] }) {
  const [audits, setAudits] = useState<DealAudit[]>(initialAudits);
  const [selected, setSelected] = useState<number | null>(initialAudits[0]?.id ?? null);
  const [input, setInput] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/audit', { cache: 'no-store' });
      if (r.ok) setAudits((await r.json()).audits);
    } catch { /* сеть мигнула */ }
  }, []);

  useEffect(() => {
    if (!audits.some((a) => a.status === 'pending' || a.status === 'collecting')) return;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [audits, refresh]);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    const r = await fetch('/api/audit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deal: input }),
    });
    if (!r.ok) { setErr((await r.json().catch(() => null))?.error ?? `Ошибка ${r.status}`); return; }
    setInput('');
    const { id } = await r.json();
    setSelected(id);
    await refresh();
  }

  const current = audits.find((a) => a.id === selected) ?? null;

  return (
    <div className="bb-page">
      <div className="bb-hero bb-aurora">
        <div className="bb-hero-row">
          <div style={{ flex: 1, minWidth: 280 }}>
            <div className="bb-hero-eyebrow">АУДИТ СДЕЛОК</div>
            <div className="bb-hero-title">Разобрать сделку за минуту</div>
            <div className="bb-hero-sub">Вставь ссылку или ID — соберём встречи, транскрипты, переписку, звонки и КП, оценим честный шанс возврата и предложим следующий шаг.</div>
            <form onSubmit={submit} style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="https://belberrycrm.bitrix24.ru/crm/deal/details/23332/ или 23332"
                style={{ flex: 1, minWidth: 260, border: '1px solid rgba(255,255,255,.25)', background: 'rgba(255,255,255,.12)', color: '#fff', borderRadius: 12, padding: '12px 15px', fontSize: 14 }} />
              <button type="submit" style={{ background: '#fff', color: 'var(--bb-indigo)', border: 0, borderRadius: 12, padding: '12px 22px', fontWeight: 700, cursor: 'pointer' }}>Запустить аудит →</button>
            </form>
            {err && <div style={{ color: '#ffd2d2', fontSize: 13, marginTop: 8 }}>{err}</div>}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, alignItems: 'start' }}>
        <div className="bb-card">
          <div className="bb-sect-head"><div className="bb-sect-ic">📁</div><h2>Аудиты</h2></div>
          {audits.length === 0 && <div style={{ color: 'var(--bb-faint)', fontSize: 13 }}>Пока пусто — запусти первый аудит.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {audits.map((a) => (
              <button key={a.id} onClick={() => setSelected(a.id)}
                style={{ textAlign: 'left', border: 0, background: a.id === selected ? 'var(--bb-violet-soft)' : 'transparent', borderRadius: 10, padding: '9px 10px', cursor: 'pointer' }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>{a.title ?? `Сделка #${a.dealId}`}</div>
                <div style={{ fontSize: 11.5, color: 'var(--bb-faint)', display: 'flex', gap: 8 }}>
                  <span>#{a.dealId}</span>
                  {a.status === 'ready'
                    ? <span style={{ fontWeight: 700, color: BAND_COLOR[a.band ?? 'low'] }}>{a.score}%</span>
                    : <span>{a.status === 'error' ? 'ошибка' : '⏳ …'}</span>}
                  {a.returnedToWork && <span style={{ color: 'var(--bb-green)' }}>✓ в работе</span>}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>{current ? <AuditDetail audit={current} onReturned={refresh} /> : <div className="bb-card" style={{ color: 'var(--bb-faint)' }}>Выбери аудит слева или запусти новый.</div>}</div>
      </div>
    </div>
  );
}
