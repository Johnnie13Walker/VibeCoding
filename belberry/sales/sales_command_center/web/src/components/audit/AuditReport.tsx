'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import type { AuditResult, DealAudit, SalesUser } from '@/lib/audit';

const STAGES: { id: string; label: string }[] = [
  { id: 'C10:NEW', label: 'Квалификация' },
  { id: 'C10:PREPAYMENT_INVOIC', label: 'Подготовка БРИФа' },
  { id: 'C10:EXECUTING', label: 'Подготовка КП' },
  { id: 'C10:UC_4SJOE4', label: 'Защита КП' },
  { id: 'C10:FINAL_INVOICE', label: 'Получить решение' },
];

const BAND_LABEL: Record<string, string> = { low: 'низкий', mid: 'средний', hi: 'высокий' };
const BAND_COLOR: Record<string, string> = { low: 'var(--bb-red)', mid: 'var(--bb-amber)', hi: 'var(--bb-green)' };
const BAND_BG: Record<string, string> = { low: '#fdeced', mid: '#fdf2e7', hi: '#e7f4ec' };

const PATTERN_LABEL: Record<string, string> = {
  KP_NO_CARD: 'КП без карточки в системе', KP_VIA_PITCH: 'КП через сторонний сервис',
  KP_OVER_BUDGET: 'КП дороже бюджета', KP_STUCK_INSIDE: 'КП лежит внутри неделями',
  CANT_DEFEND_PRICE: 'Не защитили цену', BRIEF_SPRAY: 'Стрельба по площадям',
  LABEL_NO_CONTACT: 'Метка «нет связи»', LABEL_CHANGED_MIND: 'Метка «передумали»',
  LABEL_COMPETITOR: 'Долгая пауза → конкурент', LABEL_BUDGET: 'Метка «нет бюджета»',
  TRAP_URGENCY: 'Давление срочностью', TRAP_FAKE_REASON: 'Ложная причина отвала',
  TRAP_CLIENT_WILL_CALL: '«Сам перезвоню» — закрытая дверь', TRAP_NO_VALUE: 'Не объяснили ценность',
  TRAP_COLD_HANDOVER: 'Холодная передача сделки', NO_DEFENSE: 'Защита КП не проведена',
  NON_DM_CONTACT: 'Работа не с лицом, принимающим решение', HANDOVER_NO_CONTEXT: 'Передача без контекста',
  STAGE_VS_REALITY: 'Стадия не отражает реальность', CONTACT_LOST: 'Контактное лицо ушло',
  COMPETITOR: 'Ушли к конкуренту', OTHER: 'Прочее',
};
const SEV_LABEL: Record<string, string> = { high: 'критично', med: 'существенно', low: 'умеренно' };
function patternLabel(id?: string): string {
  return (id && PATTERN_LABEL[id]) || 'Провал';
}
function money(n?: number | null): string {
  return n ? `${n.toLocaleString('ru-RU')} ₽` : '—';
}
function num(v: unknown): number {
  return typeof v === 'number' ? v : 0;
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
    <div style={{ position: 'relative', width: 180, height: 180, margin: '0 auto' }}>
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

function Section({ icon, title, hint, children }: { icon: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="bb-card">
      <div className="bb-sect-head"><div className="bb-sect-ic">{icon}</div><h2>{title}</h2>{hint && <small>{hint}</small>}</div>
      {children}
    </div>
  );
}

function Stat({ value, label, chip, flag }: { value: number | string; label: string; chip?: string; flag?: boolean }) {
  return (
    <div style={{ background: 'var(--bb-canvas)', borderRadius: 14, padding: 14 }}>
      <b style={{ fontSize: 24, fontWeight: 800, display: 'block', color: flag ? 'var(--bb-red)' : 'var(--bb-ink)' }}>{value}</b>
      <span style={{ fontSize: 11.5, color: 'var(--bb-muted)' }}>{label}</span>
      {chip && <div><span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, background: '#fdeced', color: 'var(--bb-red)', borderRadius: 6, padding: '1px 6px', marginTop: 4 }}>{chip}</span></div>}
    </div>
  );
}

export function AuditReport({ initialAudit, managers }: { initialAudit: DealAudit; managers: SalesUser[] }) {
  const [audit, setAudit] = useState<DealAudit>(initialAudit);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const r = audit.result as AuditResult | null;
  const n = r?.narrative ?? {};
  const s = (r?.signals ?? {}) as Record<string, unknown>;
  const chain = (s.responsibles_chain as string[] | undefined) ?? [];
  const [stageId, setStageId] = useState('C10:EXECUTING');
  const [responsibleId, setResponsibleId] = useState(chain.length ? String(chain[chain.length - 1]) : '');
  const [deadline] = useState(tomorrow18iso());
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDesc, setTaskDesc] = useState('');

  // самоопрос статуса, пока аудит выполняется
  const poll = useCallback(async () => {
    try {
      const res = await fetch(`/api/audit/${audit.id}`, { cache: 'no-store' });
      if (res.ok) setAudit((await res.json()).audit);
    } catch { /* сеть мигнула */ }
  }, [audit.id]);
  useEffect(() => {
    if (audit.status === 'ready' || audit.status === 'error') return;
    const t = setInterval(poll, 4000);
    return () => clearInterval(t);
  }, [audit.status, poll]);
  // подставить текст задачи из разбора, когда он появится
  useEffect(() => {
    if (n.first_task && !taskTitle) {
      setTaskTitle(n.first_task.title ?? 'Связаться по сделке');
      setTaskDesc(n.first_task.description ?? '');
    }
  }, [n.first_task, taskTitle]);

  const back = (
    <Link href="/audit" style={{ color: 'var(--bb-violet)', fontWeight: 600, textDecoration: 'none', fontSize: 13.5 }}>← к списку аудитов</Link>
  );

  if (audit.status === 'error') {
    return <div className="bb-page">{back}<div className="bb-card" style={{ marginTop: 14 }}><b>Ошибка аудита:</b> {audit.error}</div></div>;
  }
  if (audit.status !== 'ready' || !r) {
    return (
      <div className="bb-page">{back}
        <div className="bb-card bb-fade" style={{ marginTop: 14 }}>⏳ Аудит выполняется: сбор данных, расшифровка звонков и встреч, разбор. Обычно 1–2 минуты…</div>
      </div>
    );
  }

  async function returnToWork() {
    setBusy(true); setErr(null);
    const res = await fetch(`/api/audit/${audit.id}/return-to-work`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stageId, responsibleId: Number(responsibleId), deadline, taskTitle, taskDescription: taskDesc }),
    });
    setBusy(false);
    if (!res.ok) { setErr((await res.json().catch(() => null))?.error ?? `Ошибка ${res.status}`); return; }
    await poll();
    setOpen(false);
  }

  const rec = r.recovery;
  const kpCards = num(s.kp_cards);
  return (
    <div className="bb-page bb-fade">
      <div style={{ marginBottom: 14 }}>{back}</div>

      <div className="bb-card">
        <div className="bb-sect-head">
          <div className="bb-sect-ic">🔎</div>
          <h2>{r.title ?? `Сделка #${audit.dealId}`} <span style={{ color: 'var(--bb-faint)' }}>#{audit.dealId}</span></h2>
          <small>{r.company} · <a style={{ color: 'var(--bb-violet)', fontWeight: 600, textDecoration: 'none' }} target="_blank" rel="noreferrer"
            href={`https://belberrycrm.bitrix24.ru/crm/deal/details/${audit.dealId}/`}>открыть в Bitrix ↗</a></small>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 24, alignItems: 'center' }} className="bb-rec-grid">
          <Gauge score={rec.score} band={rec.band} />
          <div>
            <span style={{ display: 'inline-block', fontWeight: 800, fontSize: 13, borderRadius: 999, padding: '5px 14px', marginBottom: 10, background: BAND_BG[rec.band], color: BAND_COLOR[rec.band] }}>
              {(n.verdict_band_text ?? BAND_LABEL[rec.band] ?? '').toUpperCase()} · ожидаемая ценность {money(rec.expected_value)}
            </span>
            <div style={{ fontSize: 15, lineHeight: 1.55 }}>{n.summary}</div>
            {n.real_cause && <div style={{ marginTop: 8, fontSize: 13.5, color: 'var(--bb-muted)' }}><b>Реальная причина:</b> {n.real_cause}</div>}
            <ul style={{ listStyle: 'none', padding: 0, marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 18px' }}>
              {rec.factors.map((f, i) => (
                <li key={i} style={{ fontSize: 13, display: 'flex', gap: 8 }}>
                  <span style={{ color: f.weight > 0 ? 'var(--bb-green)' : 'var(--bb-red)', fontWeight: 700 }}>{f.weight > 0 ? '＋' : '－'}</span>
                  <span>{f.label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <Section icon="📊" title="Что в системе">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
          <Stat value={kpCards} label="карточек КП в системе" flag={kpCards === 0 && !!s.kp_sent} chip={kpCards === 0 && s.kp_via_pitch ? 'КП мимо системы' : undefined} />
          <Stat value={num(s.meetings_total)} label="встреч" />
          <Stat value={num(s.briefs_total)} label="брифов" flag={num(s.briefs_total) >= 3} chip={num(s.briefs_total) >= 3 ? 'много на 1 запрос' : undefined} />
          <Stat value={num(s.handover_count)} label="передач менеджера" flag={num(s.handover_count) >= 2} chip={num(s.handover_count) >= 2 ? 'без контекста' : undefined} />
          <Stat value={num(s.calls_total)} label="звонков" />
        </div>
      </Section>

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
        <Section icon="☎" title="Анализ звонков" hint={`записей: ${r.call_recordings?.length ?? 0}`}>
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
            <div key={i} style={{ display: 'flex', gap: 12, padding: '11px 0', borderBottom: '1px solid var(--bb-line)' }}>
              <span style={{ flex: '0 0 26px', height: 26, borderRadius: 8, background: '#fdeced', color: 'var(--bb-red)', fontWeight: 800, fontSize: 13, display: 'grid', placeItems: 'center' }}>{i + 1}</span>
              <div style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                <b>{f.title}</b>
                <span style={{ display: 'inline-block', fontSize: 10.5, fontWeight: 700, background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)', borderRadius: 6, padding: '1px 7px', marginLeft: 8 }}>{patternLabel(f.pattern_id)}</span>
                {f.severity && SEV_LABEL[f.severity] && <span style={{ fontSize: 11, color: 'var(--bb-faint)', marginLeft: 6 }}>{SEV_LABEL[f.severity]}</span>}
                <div style={{ color: 'var(--bb-muted)', marginTop: 3 }}>{f.detail}</div>
              </div>
            </div>
          ))}
        </Section>
      )}

      {!!n.what_would_save_it?.length && (
        <Section icon="⤷" title="Что спасло бы сделку">
          <ul style={{ margin: 0, paddingLeft: 18 }}>{n.what_would_save_it.map((w, i) => <li key={i} style={{ fontSize: 13.5, marginBottom: 6 }}>{w}</li>)}</ul>
        </Section>
      )}

      {!!n.next_steps?.length && (
        <div style={{ background: 'linear-gradient(135deg,#f0eefb,#fbfaff)', border: '1px solid #d9d3f7', borderRadius: 18, padding: 20, marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>🎯 Предлагаемый следующий шаг</h2>
          <ol style={{ margin: 0, paddingLeft: 20 }}>{n.next_steps.map((stp, i) => <li key={i} style={{ fontSize: 13.5, lineHeight: 1.6, marginBottom: 4 }}>{stp}</li>)}</ol>
        </div>
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

      {/* Следующий шаг: вернуть в работу + поставить задачу */}
      <Section icon="⚡" title="Действия">
        {audit.returnedToWork ? (
          <div style={{ color: 'var(--bb-green)', fontWeight: 600 }}>
            ✓ Сделка возвращена в работу{audit.taskId ? `, задача №${audit.taskId} поставлена` : ''}.
          </div>
        ) : !open ? (
          <button onClick={() => setOpen(true)}
            style={{ background: 'var(--bb-violet)', color: '#fff', border: 0, borderRadius: 12, padding: '12px 18px', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}>
            ↩︎ Вернуть в работу + поставить задачу
          </button>
        ) : (
          <div style={{ border: '1px dashed #d9d3f7', borderRadius: 14, padding: 16, background: '#fbfaff' }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10, fontSize: 13, alignItems: 'center' }}>
              <label>Стадия:{' '}
                <select value={stageId} onChange={(e) => setStageId(e.target.value)} style={{ border: '1px solid var(--bb-line)', borderRadius: 8, padding: '4px 8px' }}>
                  {STAGES.map((st) => <option key={st.id} value={st.id}>{st.label}</option>)}
                </select>
              </label>
              <label>Ответственный:{' '}
                <select value={responsibleId} onChange={(e) => setResponsibleId(e.target.value)} style={{ border: '1px solid var(--bb-line)', borderRadius: 8, padding: '4px 8px' }}>
                  <option value="">— выбрать —</option>
                  {managers.map((m) => <option key={m.id} value={String(m.id)}>{m.name}</option>)}
                </select>
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
      </Section>
    </div>
  );
}
