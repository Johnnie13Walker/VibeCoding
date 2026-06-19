'use client';

import { useMemo, useState } from 'react';
import { buildManagerScores, type MeetingItem } from '@/lib/meetings-shared';

const TYPE_RU: Record<string, string> = { briefing: 'Брифинг', defense: 'Защита КП', other: 'Прочее' };
const TRANSCRIPT_RU: Record<string, string> = { no_transcript: 'Нет транскрипта' };

function fmtDate(d: string): string {
  const [, m, da] = d.split('-');
  return da && m ? `${da}.${m}` : d;
}
function scoreColor(s: number | null): string {
  return s == null ? '#cfcde0' : s >= 8 ? '#1fb866' : s >= 6 ? '#e9a13a' : '#e0565f';
}
function hasGap(m: MeetingItem): boolean {
  return m.transcript !== 'ok';
}

const cellSelect: React.CSSProperties = {
  font: 'inherit', fontSize: 14, padding: '8px 10px', border: '1px solid var(--bb-line)',
  borderRadius: 10, background: '#fafafe', color: 'var(--bb-ink, #191730)', minWidth: 140,
};
const pill: React.CSSProperties = { fontSize: 13, color: 'var(--bb-muted)', background: 'var(--bb-soft,#f3f2fb)', borderRadius: 999, padding: '7px 13px' };
const bxLink: React.CSSProperties = { color: '#5b4fe0', fontWeight: 600, textDecoration: 'none', whiteSpace: 'nowrap' };

export function MeetingsView({ items }: { items: MeetingItem[] }) {
  const [fDate, setDate] = useState('');
  const [fMgr, setMgr] = useState('');
  const [fType, setType] = useState('');
  const [fScore, setScore] = useState('');
  const [fState, setState] = useState('');
  const [fQ, setQ] = useState('');
  const [selected, setSelected] = useState<number | null>(items.find((m) => !hasGap(m))?.id ?? items[0]?.id ?? null);

  const dates = useMemo(() => [...new Set(items.map((m) => m.date))].sort().reverse(), [items]);
  const mgrs = useMemo(() => [...new Set(items.map((m) => m.manager))].sort(), [items]);

  const baseRows = useMemo(() => {
    const q = fQ.trim().toLowerCase();
    return items.filter((m) => {
      if (fDate && m.date !== fDate) return false;
      if (fType && m.type !== fType) return false;
      if (fScore && m.score == null) return false;
      if (fScore === 'hi' && (m.score ?? 0) < 8) return false;
      if (fScore === 'mid' && ((m.score ?? 0) < 6 || (m.score ?? 0) > 7)) return false;
      if (fScore === 'lo' && (m.score ?? 99) > 5) return false;
      if (fState === 'notranscript' && !hasGap(m)) return false;
      if (fState === 'nosummary' && m.summarySent !== false) return false;
      if (fState === 'problem' && !(m.score != null && m.score <= 5)) return false;
      if (q && !m.domain.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [items, fDate, fType, fScore, fState, fQ]);
  const rows = useMemo(
    () => baseRows.filter((m) => !fMgr || m.manager === fMgr).sort((a, b) => (b.date + b.time).localeCompare(a.date + a.time)),
    [baseRows, fMgr],
  );
  const mgrScores = useMemo(() => buildManagerScores(baseRows), [baseRows]);

  const selectedMeeting = items.find((m) => m.id === selected) ?? null;

  const an = rows.filter((m) => m.score != null);
  const avg = an.length ? (an.reduce((a, m) => a + (m.score as number), 0) / an.length).toFixed(1) : '—';
  const summKnown = rows.filter((m) => m.summarySent !== null);
  const summPct = summKnown.length ? Math.round((summKnown.filter((m) => m.summarySent).length / summKnown.length) * 100) : null;
  const gaps = rows.filter(hasGap).length;

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ paddingBottom: 18 }}>
        <div className="bb-hero-eyebrow">Отдел продаж · качество встреч</div>
        <h1 className="bb-hero-title">Анализ встреч</h1>
        <div className="bb-hero-sub">
          Разбор проведённых встреч по транскриптам · контроль итогов клиенту и записи · только ОП и РОП
        </div>
      </div>

      {/* фильтры */}
      <div className="bb-card" style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <Field label="Дата">
          <select style={cellSelect} value={fDate} onChange={(e) => setDate(e.target.value)}>
            <option value="">Все даты</option>
            {dates.map((d) => <option key={d} value={d}>{fmtDate(d)}.{d.slice(0, 4)}</option>)}
          </select>
        </Field>
        <Field label="Менеджер">
          <select style={cellSelect} value={fMgr} onChange={(e) => setMgr(e.target.value)}>
            <option value="">Все менеджеры</option>
            {mgrs.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </Field>
        <Field label="Тип">
          <select style={cellSelect} value={fType} onChange={(e) => setType(e.target.value)}>
            <option value="">Все</option><option value="briefing">Брифинг</option><option value="defense">Защита КП</option>
          </select>
        </Field>
        <Field label="Балл">
          <select style={cellSelect} value={fScore} onChange={(e) => setScore(e.target.value)}>
            <option value="">Любой</option><option value="hi">Сильные (8–10)</option><option value="mid">Средние (6–7)</option><option value="lo">Слабые (1–5)</option>
          </select>
        </Field>
        <Field label="Состояние">
          <select style={cellSelect} value={fState} onChange={(e) => setState(e.target.value)}>
            <option value="">Все</option><option value="notranscript">Нет транскрипта</option><option value="nosummary">Итоги НЕ отправлены</option><option value="problem">Проблемные (≤5)</option>
          </select>
        </Field>
        <Field label="Поиск">
          <input type="search" style={{ ...cellSelect, minWidth: 180 }} value={fQ} onChange={(e) => setQ(e.target.value)} placeholder="домен / клиент" />
        </Field>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span style={pill}>Встреч: <b style={{ color: 'var(--bb-ink,#191730)' }}>{rows.length}</b></span>
          <span style={pill}>Ср. балл: <b style={{ color: 'var(--bb-ink,#191730)' }}>{avg}</b></span>
          {summPct != null ? <span style={pill}>Итоги: <b style={{ color: 'var(--bb-ink,#191730)' }}>{summPct}%</b></span> : null}
          {gaps ? <span style={{ ...pill, background: 'var(--bb-amber-bg,#fdf2e3)', color: '#e07b1a' }}>Без транскрипта: <b>{gaps}</b></span> : null}
        </div>
      </div>

      {/* рейтинг менеджеров */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 17, fontWeight: 800 }}>Средний балл по менеджерам</h2>
        <p style={{ color: 'var(--bb-faint)', fontSize: 12.5, margin: '0 0 12px' }}>
          Только отдел продаж и РОП. Клик по менеджеру — фильтрует встречи ниже. Учитываются выбранные дата/тип/состояние.
        </p>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, whiteSpace: 'nowrap' }}>
            <thead>
              <tr style={{ color: 'var(--bb-faint)', fontSize: 12 }}>
                {['Менеджер', 'Встреч', 'Ср. балл', 'Брифинг', 'Защита КП', 'Итоги %', 'Бюджет %', 'След.шаг %', 'Без транскр.'].map((h, i) => (
                  <th key={h} style={{ padding: '8px 10px', borderBottom: '1px solid var(--bb-line)', textAlign: i === 0 ? 'left' : 'right' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {mgrScores.map((s) => (
                <tr key={s.managerId} style={fMgr === s.name ? { background: '#f3f0ff' } : undefined}>
                  <td
                    style={{ padding: '9px 10px', borderBottom: '1px solid var(--bb-line)', textAlign: 'left', fontWeight: 600, cursor: 'pointer', color: fMgr === s.name ? '#5b4fe0' : undefined }}
                    onClick={() => setMgr(fMgr === s.name ? '' : s.name)}
                  >
                    {s.name}
                  </td>
                  <td className="tabular" style={tdR}>{s.count}</td>
                  <td style={tdR}>
                    <span style={{ display: 'inline-grid', placeItems: 'center', width: 34, height: 26, borderRadius: 8, color: '#fff', fontWeight: 800, fontSize: 13, background: scoreColor(s.avg) }}>
                      {s.avg == null ? '—' : s.avg.toFixed(1)}
                    </span>
                  </td>
                  <td className="tabular" style={tdR}>{s.briefingAvg?.toFixed(1) ?? '—'}</td>
                  <td className="tabular" style={tdR}>{s.defenseAvg?.toFixed(1) ?? '—'}</td>
                  <td className="tabular" style={tdR}>{s.summaryPct == null ? '—' : `${s.summaryPct}%`}</td>
                  <td className="tabular" style={tdR}>{s.budgetPct == null ? '—' : `${s.budgetPct}%`}</td>
                  <td className="tabular" style={tdR}>{s.nextStepPct}%</td>
                  <td className="tabular" style={{ ...tdR, color: s.gaps ? '#e07b1a' : undefined, fontWeight: s.gaps ? 700 : 400 }}>{s.gaps || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* список + разбор */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,380px) 1fr', gap: 16, alignItems: 'start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="bb-card" style={{ padding: 0, maxHeight: '80vh', overflowY: 'auto' }}>
          {rows.length === 0 ? (
            <p style={{ padding: 30, textAlign: 'center', color: 'var(--bb-faint)' }}>Нет встреч под фильтр</p>
          ) : (
            rows.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m.id)}
                style={{
                  display: 'flex', gap: 12, width: '100%', textAlign: 'left', cursor: 'pointer',
                  padding: '13px 15px', borderBottom: '1px solid var(--bb-line)', background: selected === m.id ? '#f1eeff' : hasGap(m) ? '#fffaf3' : 'transparent',
                  border: 'none', boxShadow: selected === m.id ? 'inset 3px 0 0 #6f5ff2' : 'none',
                }}
              >
                <span style={{ flex: '0 0 auto', width: 38, height: 38, borderRadius: 11, display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 15, color: '#fff', background: scoreColor(m.score) }}>
                  {m.score == null ? '—' : m.score}
                </span>
                <span style={{ minWidth: 0, flex: 1 }}>
                  <span style={{ display: 'block', fontWeight: 700, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.domain}</span>
                  <span style={{ display: 'block', fontSize: 12, color: 'var(--bb-faint)', marginTop: 2 }}>{fmtDate(m.date)} {m.time} · {m.manager}</span>
                  <span style={{ fontSize: 12.5, color: hasGap(m) ? '#e07b1a' : 'var(--bb-muted)', marginTop: 4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                    {hasGap(m) ? 'Нет транскрипта — разбор не выполнен' : m.verdict || '—'}
                  </span>
                  <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                    <Mini text={TYPE_RU[m.type ?? 'other']} kind={m.type === 'defense' ? 'df' : 'bf'} />
                    {hasGap(m) ? <Mini text={`⚠ ${TRANSCRIPT_RU[m.transcript]}`} kind="warn" /> : null}
                    {m.summarySent === true ? <Mini text="Итоги ✓" kind="ok" /> : m.summarySent === false ? <Mini text="Итоги ✗" kind="no" /> : null}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
        <ScoreLogic />
        </div>

        <div className="bb-card">
          {selectedMeeting ? <Detail m={selectedMeeting} /> : <p style={{ padding: 30, textAlign: 'center', color: 'var(--bb-faint)' }}>← Выбери встречу из списка</p>}
        </div>
      </div>
    </div>
  );
}

// ── «Как считается балл» — пояснение логики оценки (узкая левая колонка) ──────
const SCORE_BANDS: { range: string; bg: string; ttl: string; desc: string }[] = [
  { range: '9–10', bg: 'linear-gradient(135deg,#3a9c63,#2c7a4a)', ttl: 'Образцовая', desc: 'весь чек-лист ✅, бюджет+ЛПР+сроки, клиент взял обязательство, дата зафиксирована' },
  { range: '8', bg: '#3a9c63', ttl: 'Сильная', desc: 'почти весь ✅ (≤1 ⚠️), но обязательство мягкое или упущен 1 ключевой пункт' },
  { range: '6–7', bg: '#c97a1e', ttl: 'Рабочая, с провисами', desc: '2–3 пункта ⚠️/❌, размытый следующий шаг' },
  { range: '4–5', bg: '#dd7a3a', ttl: 'Слабая', desc: 'анкета вместо диалога / нет бюджета / кейсов / след. шага' },
  { range: '1–3', bg: 'var(--bb-red)', ttl: 'Провал', desc: 'клиент потерян, нет потребности и шага' },
];
const factorStyle: React.CSSProperties = { fontSize: 11, fontWeight: 600, background: '#f4f2fb', color: 'var(--bb-indigo)', borderRadius: 999, padding: '3px 9px' };
const chipStyle: React.CSSProperties = { fontSize: 11, color: 'var(--bb-ink)', background: '#f6f4f1', border: '1px solid var(--bb-line)', borderRadius: 7, padding: '3px 8px' };
function tagStyle(kind: 'br' | 'df'): React.CSSProperties {
  return { fontSize: 10, fontWeight: 700, borderRadius: 5, padding: '2px 6px', ...(kind === 'br' ? { background: '#eef0ff', color: '#4a3fd0' } : { background: '#fdeef6', color: '#c0297e' }) };
}

function ScoreLogic() {
  const [open, setOpen] = useState(true);
  return (
    <div className="bb-card" style={{ padding: '14px 16px' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left' }}
      >
        <span style={{ width: 26, height: 26, borderRadius: 8, display: 'grid', placeItems: 'center', background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)', flex: '0 0 26px', fontSize: 13 }}>★</span>
        <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-.01em' }}>Как считается балл</span>
        <span style={{ marginLeft: 'auto', color: 'var(--bb-faint)', fontSize: 13 }}>{open ? '▾' : '▸'}</span>
      </button>

      {open ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: 'var(--bb-muted)', lineHeight: 1.45, marginBottom: 12 }}>
            Балл 1–10 ставит ИИ по транскрипту — это <b style={{ color: 'var(--bb-ink)' }}>качество проведения</b> встречи (как отработал менеджер), а не статус сделки. Строится из 4 факторов:
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 14 }}>
            <span style={factorStyle}>✓ Чек-лист</span>
            <span style={factorStyle}>→ Следующий шаг</span>
            <span style={factorStyle}>📊 Аргументация</span>
            <span style={factorStyle}>🤝 Обязательство</span>
          </div>

          {SCORE_BANDS.map((b, i) => (
            <div key={b.range} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i === 0 ? 'none' : '1px solid #f3efe9' }}>
              <span style={{ flex: '0 0 42px', width: 42, height: 30, borderRadius: 8, display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 13, color: '#fff', background: b.bg }}>{b.range}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 12.5, fontWeight: 700, lineHeight: 1.2 }}>{b.ttl}</span>
                <span style={{ display: 'block', fontSize: 11, color: 'var(--bb-muted)', marginTop: 1, lineHeight: 1.35 }}>{b.desc}</span>
              </span>
            </div>
          ))}

          <div style={{ height: 1, background: 'var(--bb-line)', margin: '13px 0 11px' }} />

          <div style={{ fontSize: 11.5, fontWeight: 800, display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
            <span style={tagStyle('br')}>Брифинг</span> чек-лист
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 11 }}>
            {['диалог-не-анкета', 'потребность', 'кейсы', 'бюджет', 'след. шаг'].map((c) => (
              <span key={c} style={chipStyle}>{c === 'бюджет' ? <b>бюджет</b> : c}</span>
            ))}
          </div>
          <div style={{ fontSize: 11.5, fontWeight: 800, display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
            <span style={tagStyle('df')}>Защита КП</span> чек-лист
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 11 }}>
            {['кейсы (обяз.)', 'аргументация цифрами', 'запрос след. шагов', 'итоги клиенту'].map((c) => (
              <span key={c} style={chipStyle}>{c}</span>
            ))}
          </div>

          <div style={{ fontSize: 11, color: 'var(--bb-muted)', lineHeight: 1.45, background: '#f7f6fc', border: '1px solid var(--bb-line)', borderRadius: 9, padding: '9px 11px', marginBottom: 10 }}>
            🤝 <b style={{ color: 'var(--bb-ink)' }}>«Взял обязательство»</b> — клиент дал конкретное обещание двигаться дальше (действие + дата): «пришлю реквизиты до пятницы», «созвон во вторник», «выношу на совет директоров». А «подумаю / обсудим внутри» без даты — это <b>мягкое</b> обязательство (потолок балла ≈8), «нет» — клиент ушёл без шага.
          </div>

          <div style={{ fontSize: 11, color: 'var(--bb-faint)', lineHeight: 1.45 }}>
            <b style={{ color: 'var(--bb-muted)' }}>Ориентиры:</b> брифинг без бюджета ≈ 5–6; крепкая защита с мягким обязательством ≈ 8. Цель — <b>≥7</b>.
          </div>
        </div>
      ) : null}
    </div>
  );
}

const tdR: React.CSSProperties = { padding: '9px 10px', borderBottom: '1px solid var(--bb-line)', textAlign: 'right' };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ fontSize: 12, color: 'var(--bb-faint)', display: 'block', marginBottom: 3, fontWeight: 600 }}>{label}</label>
      {children}
    </div>
  );
}

const MINI: Record<string, React.CSSProperties> = {
  bf: { background: '#eef', color: '#4a3fd0' },
  df: { background: '#fdeef6', color: '#c0297e' },
  ok: { background: '#e9f8ef', color: '#15a85c' },
  no: { background: '#fdeced', color: '#d4202e' },
  warn: { background: '#fdf2e3', color: '#e07b1a' },
};
function Mini({ text, kind }: { text: string; kind: keyof typeof MINI }) {
  return <span style={{ ...MINI[kind], fontSize: 11, fontWeight: 700, borderRadius: 6, padding: '2px 7px' }}>{text}</span>;
}

function Gate({ label, ok, textOk, textNo }: { label: string; ok: boolean | null; textOk: string; textNo: string }) {
  const cls = ok === true ? '#15a85c' : ok === false ? '#d4202e' : '#e07b1a';
  const sym = ok === true ? '✓' : ok === false ? '✗' : '?';
  const txt = ok === true ? textOk : ok === false ? textNo : 'не вычислено';
  return (
    <div style={{ flex: 1, minWidth: 150, border: '1px solid var(--bb-line)', borderRadius: 12, padding: '11px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 30, height: 30, borderRadius: 9, display: 'grid', placeItems: 'center', fontWeight: 800, color: '#fff', background: cls, flex: '0 0 auto' }}>{sym}</span>
      <span>
        <span style={{ display: 'block', fontSize: 12, color: 'var(--bb-faint)', fontWeight: 600 }}>{label}</span>
        <span style={{ display: 'block', fontSize: 14, fontWeight: 700 }}>{txt}</span>
      </span>
    </div>
  );
}

function KpAssessment({ value, note }: { value: 'обоснованно' | 'преждевременно' | 'не_применимо'; note: string }) {
  if (value === 'не_применимо') return null;
  const ok = value === 'обоснованно';
  const bg = ok ? '#e9f8ef' : '#fdf2e3';
  const border = ok ? '#bfe8cf' : '#f3d9b0';
  const color = ok ? '#15a85c' : '#e07b1a';
  const title = ok ? '✅ КП обосновано — потребность выявлена' : '⚠️ КП преждевременно — потребность нормально не выявлена';
  return (
    <div style={{ margin: '4px 0 14px', padding: '13px 16px', borderRadius: 12, background: bg, border: `1px solid ${border}` }}>
      <div style={{ fontSize: 14, fontWeight: 800, color }}>{title}</div>
      {note ? <div style={{ fontSize: 13, color: 'var(--bb-muted)', marginTop: 4, lineHeight: 1.45 }}>{note}</div> : null}
    </div>
  );
}

function Obs({ items, kind }: { items: { text: string; metric?: string }[]; kind: 'good' | 'risk' }) {
  if (!items.length) return <p style={{ color: 'var(--bb-faint)', fontSize: 13 }}>—</p>;
  const mark = kind === 'good' ? '✓' : '!';
  const color = kind === 'good' ? '#15a85c' : '#d4202e';
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 9 }}>
      {items.map((o, i) => (
        <li key={i} style={{ fontSize: 13.5, lineHeight: 1.45, paddingLeft: 22, position: 'relative' }}>
          <span style={{ position: 'absolute', left: 2, color, fontWeight: 800 }}>{mark}</span>
          {o.text}
          {o.metric ? <span style={{ display: 'block', fontSize: 12, color: 'var(--bb-faint)', marginTop: 1 }}>{o.metric}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function NichesLine({ niches }: { niches: string[] }) {
  if (!niches.length) return null;
  return (
    <div style={{ marginTop: 12, paddingTop: 11, borderTop: '1px dashed #cfe0d4', fontSize: 13, color: 'var(--bb-muted)', lineHeight: 1.5 }}>
      <b style={{ color: 'var(--bb-ink)' }}>Заявлен опыт по нишам</b> (без конкретного кейса):{' '}
      {niches.map((n) => (
        <span key={n} style={{ display: 'inline-block', fontSize: 12, background: '#eef3ef', color: '#3f7a56', borderRadius: 7, padding: '2px 8px', margin: '2px 3px 0 0' }}>{n}</span>
      ))}
    </div>
  );
}

function CasesBlock({ cases, niches, isDefense }: { cases: { client: string; service: string; result: string; quote: string }[]; niches: string[]; isDefense: boolean }) {
  if (cases.length > 0) {
    return (
      <div style={{ margin: '6px 0 16px', padding: '15px 17px', borderRadius: 13, background: '#f4fbf6', border: '1px solid #d8e9dd' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 800 }}>📁 Кейсы</span>
          <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 9px', background: '#e9f6ee', color: '#2c7a4a' }}>{cases.length === 1 ? 'показан' : 'показаны'} · {cases.length}</span>
        </div>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 13 }}>
          {cases.map((c, i) => (
            <li key={i} style={{ display: 'flex', gap: 10, fontSize: 14, lineHeight: 1.5 }}>
              <span style={{ color: '#2c7a4a', fontWeight: 800, flex: '0 0 auto' }}>·</span>
              <span style={{ minWidth: 0 }}>
                <b>{c.client}</b>
                {c.service ? <span style={{ fontSize: 11.5, fontWeight: 700, color: '#4a3fd0', background: '#eef0ff', borderRadius: 6, padding: '1px 7px', marginLeft: 5 }}>{c.service}</span> : null}
                {c.result ? <div style={{ marginTop: 2 }}>{c.result}</div> : null}
                {c.quote ? <div style={{ fontSize: 12.5, color: 'var(--bb-faint)', fontStyle: 'italic', marginTop: 3 }}>«{c.quote.replace(/^«|»$/g, '')}»</div> : null}
              </span>
            </li>
          ))}
        </ul>
        <NichesLine niches={niches} />
      </div>
    );
  }
  // конкретных кейсов нет (разбор есть)
  return (
    <div style={{ margin: '6px 0 16px', padding: '15px 17px', borderRadius: 13, background: '#fdf6ee', border: '1px solid #f0e0c8' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 6 }}>
        <span style={{ fontSize: 14, fontWeight: 800 }}>📁 Кейсы</span>
        <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 9px', background: '#fdf2e7', color: '#c97a1e' }}>не показаны</span>
      </div>
      <div style={{ fontSize: 13.5, color: '#9a6a1d', lineHeight: 1.45 }}>
        Конкретные кейсы (бренд + цифры) на встрече не приводились.{isDefense ? ' Для защиты КП кейсы обязательны — это риск для следующего шага.' : ''}
      </div>
      <NichesLine niches={niches} />
    </div>
  );
}

function Detail({ m }: { m: MeetingItem }) {
  const chip = (
    <span style={{ fontSize: 12, fontWeight: 700, borderRadius: 7, padding: '3px 9px', ...(m.type === 'defense' ? MINI.df : MINI.bf) }}>
      {TYPE_RU[m.type ?? 'other']}
    </span>
  );
  const head = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
      <span style={{ width: 54, height: 54, borderRadius: 14, display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 20, color: '#fff', background: scoreColor(m.score) }}>{m.score ?? '—'}</span>
      <div style={{ flex: 1, minWidth: 200 }}>
        <h2 style={{ margin: 0, fontSize: 21, fontWeight: 800 }}>{m.domain} {chip}</h2>
        <div style={{ color: 'var(--bb-muted)', fontSize: 13, marginTop: 4 }}>
          {fmtDate(m.date)}.{m.date.slice(0, 4)} {m.time} · {m.manager}
          {m.dealId ? <> · <a href={`https://belberrycrm.bitrix24.ru/crm/deal/details/${m.dealId}/`} target="_blank" rel="noreferrer" style={bxLink}>Сделка в Битрикс24 ↗</a></> : null}
          {' · '}<a href={`https://belberrycrm.bitrix24.ru/crm/type/1048/details/${m.id}/`} target="_blank" rel="noreferrer" style={bxLink}>Встреча в Битрикс24 ↗</a>
        </div>
      </div>
    </div>
  );

  if (hasGap(m)) {
    return (
      <div>
        {head}
        <div style={{ marginTop: 18, padding: '18px 20px', borderRadius: 14, background: '#fdf2e3', border: '1px solid #f3d9b0' }}>
          <h3 style={{ margin: '0 0 6px', color: '#e07b1a', fontSize: 16 }}>⚠ Встреча не разобрана</h3>
          <p style={{ margin: 0, fontSize: 13.5, color: '#7a5a23', lineHeight: 1.5 }}>
            Транскрибация не приложена к сделке — LLM-разбор не выполнен. Прикрепите расшифровку встречи, чтобы появился анализ качества.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {head}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '18px 0' }}>
        <Gate label="Итоги клиенту" ok={m.summarySent} textOk="Отправлены" textNo="Не отправлены" />
        <Gate label="Бюджет" ok={m.budgetNamed} textOk="Назван" textNo="Не вскрыт" />
        <Gate label="Следующий шаг" ok={!!m.nextStep} textOk="Зафиксирован" textNo="Нет" />
        <Gate label="Запись/транскрипт" ok textOk="Есть" textNo="" />
      </div>
      {m.products.length ? (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', margin: '4px 0 14px' }}>
          <span style={{ fontSize: 13, color: 'var(--bb-faint)', fontWeight: 600 }}>Обсуждали:</span>
          {m.products.map((p) => (
            <span key={p} style={{ fontSize: 12.5, fontWeight: 700, borderRadius: 7, padding: '3px 10px', background: '#eef', color: '#4a3fd0' }}>{p}</span>
          ))}
        </div>
      ) : null}
      {m.kpAssessment ? <KpAssessment value={m.kpAssessment} note={m.kpAssessmentNote} /> : null}
      {m.verdict ? <div style={{ margin: '14px 0', padding: '14px 16px', borderRadius: 12, background: 'var(--bb-soft,#f3f2fb)', fontSize: 15, lineHeight: 1.5, borderLeft: '4px solid #6f5ff2' }}>{m.verdict}</div> : null}

      {m.clientNeeds.length ? (
        <div style={{ margin: '14px 0' }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, margin: '0 0 10px' }}>🎯 Реальные потребности и боли</h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {m.clientNeeds.map((n, i) => (
              <li key={i} style={{ fontSize: 13.5, lineHeight: 1.45 }}>
                <b>{n.need}</b>{n.pain ? <> — <span style={{ color: 'var(--bb-muted)' }}>{n.pain}</span></> : null}
                {n.evidence ? <div style={{ fontSize: 12.5, color: 'var(--bb-faint)', marginTop: 2 }}>«{n.evidence.replace(/^«|»$/g, '')}»</div> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="bb-grid" style={{ gridTemplateColumns: 'repeat(2,1fr)', gap: 18, margin: '18px 0' }}>
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 800, margin: '0 0 10px' }}>✅ Что прошло хорошо</h3>
          <Obs items={m.good} kind="good" />
        </div>
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 800, margin: '0 0 10px' }}>⚠️ Риски и зоны роста</h3>
          <Obs items={m.risk} kind="risk" />
        </div>
      </div>
      {m.nextStep ? (
        <div style={{ margin: '6px 0 18px', padding: '14px 16px', borderRadius: 12, border: '1px solid #e6e3fb', background: '#faf9ff' }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 800 }}>🎯 Следующий шаг</h3>
          {m.nextStep.what ? <div style={{ fontSize: 13.5 }}><span style={{ color: 'var(--bb-muted)' }}>Что:</span> <b>{m.nextStep.what}</b></div> : null}
          <div style={{ fontSize: 13.5, marginTop: 5 }}>
            {m.nextStep.who ? <><span style={{ color: 'var(--bb-muted)' }}>Кто:</span> <b>{m.nextStep.who}</b> &nbsp;</> : null}
            {m.nextStep.deadline ? <><span style={{ color: 'var(--bb-muted)' }}>Дедлайн:</span> <b>{m.nextStep.deadline}</b></> : null}
          </div>
        </div>
      ) : null}
      {(m.decisionMakers || m.currentSituation || m.budgetSignals || m.dialogQuality) ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12, margin: '6px 0 16px' }}>
          <Info label="ЛПР и роли" text={m.decisionMakers} />
          <Info label="Текущая ситуация / конкуренты" text={m.currentSituation} />
          <Info label="Бюджет и срочность" text={m.budgetSignals} />
          <Info label="Качество диалога" text={m.dialogQuality} />
        </div>
      ) : null}

      {m.cases != null ? <CasesBlock cases={m.cases} niches={m.niches} isDefense={m.type === 'defense'} /> : null}

      {m.coaching ? (
        <div style={{ margin: '6px 0 16px', padding: '13px 16px', borderRadius: 12, background: '#eef6ff', border: '1px solid #cfe2fb' }}>
          <div style={{ fontSize: 14, fontWeight: 800, color: '#2563c9' }}>🧭 Коучинг менеджеру</div>
          <div style={{ fontSize: 13.5, color: 'var(--bb-muted)', marginTop: 4, lineHeight: 1.45, whiteSpace: 'pre-line' }}>{m.coaching}</div>
        </div>
      ) : null}

      {m.keyQuotes.length ? (
        <div style={{ margin: '6px 0 16px' }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, margin: '0 0 8px' }}>💬 Ключевые цитаты клиента</h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
            {m.keyQuotes.map((q, i) => (
              <li key={i} style={{ fontSize: 13.5, color: 'var(--bb-ink,#191730)', borderLeft: '3px solid #d8d5f0', paddingLeft: 12, fontStyle: 'italic' }}>«{q.replace(/^«|»$/g, '')}»</li>
            ))}
          </ul>
        </div>
      ) : null}

      {m.conclusion ? <div style={{ fontSize: 13.5, color: 'var(--bb-muted)', lineHeight: 1.5, borderTop: '1px solid var(--bb-line)', paddingTop: 14 }}><b>Системный вывод:</b> {m.conclusion}</div> : null}
    </div>
  );
}

function Info({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <div style={{ border: '1px solid var(--bb-line)', borderRadius: 12, padding: '11px 14px' }}>
      <div style={{ fontSize: 12, color: 'var(--bb-faint)', fontWeight: 600, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 13.5, lineHeight: 1.4 }}>{text}</div>
    </div>
  );
}
