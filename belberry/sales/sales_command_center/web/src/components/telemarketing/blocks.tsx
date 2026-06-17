import type {
  TmKpis,
  TmManagerRow,
  TmMeetingsResult,
  TmMicroFunnel,
  TmMonthlyRow,
  TmOutreach,
  TmPlanFact,
  TmRejections,
  TmHeatmap,
  TmMeetingQuality,
  TmAlert,
} from '@/lib/telemarketing-shared';

const nf = (n: number): string => n.toLocaleString('ru-RU');
const pp = (v: number | null): string => (v != null ? `${v}%` : '—');

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const chars = parts.length >= 2 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return chars.toUpperCase();
}

const ava: React.CSSProperties = {
  width: 30, height: 30, flex: '0 0 30px', borderRadius: '50%', display: 'grid', placeItems: 'center',
  background: 'linear-gradient(135deg,#8b80ff,#5b50d6)', color: '#fff', fontWeight: 700, fontSize: 11,
};

const cell: React.CSSProperties = { padding: '10px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' };

function Mini({ label, value, sub, tone, delta }: { label: string; value: string; sub?: string; tone?: 'good' | 'warn'; delta?: React.ReactNode }) {
  const bg = tone === 'good' ? 'linear-gradient(180deg,#f4faf6,#fff)' : tone === 'warn' ? 'linear-gradient(180deg,#fdf4ee,#fff)' : '#fff';
  return (
    <div style={{ background: bg, border: '1px solid var(--bb-line)', borderRadius: 16, padding: '15px 17px', boxShadow: 'var(--bb-shadow)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.05 }}>{value}</div>
        {delta ?? null}
      </div>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 6 }}>{label}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 3 }}>{sub}</div> : null}
    </div>
  );
}

// Δ-пилюля к аналогичному периоду прошлого месяца (▲/▼ + значение). Зелёный рост,
// красный спад; для долей — в процентных пунктах (пп), для счётчиков — в %.
function DeltaTag({ dir, text, title }: { dir: 'up' | 'down' | 'flat'; text: string; title?: string }) {
  const c = dir === 'up' ? { bg: '#e7f4ec', fg: 'var(--bb-green)', a: '↑' } : dir === 'down' ? { bg: '#fdeced', fg: 'var(--bb-red)', a: '↓' } : { bg: '#eef0f4', fg: 'var(--bb-muted)', a: '→' };
  return (
    <span title={title} className="tabular" style={{ background: c.bg, color: c.fg, fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '2px 8px', lineHeight: 1.5, whiteSpace: 'nowrap' }}>
      {c.a} {text}
    </span>
  );
}
function deltaCount(cur: number, prev: number): React.ReactNode {
  if (prev <= 0) return cur > 0 ? <DeltaTag dir="up" text="новое" title="в прошлом периоде 0" /> : null;
  const pct = Math.round(((cur - prev) / prev) * 100);
  return <DeltaTag dir={pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat'} text={`${pct > 0 ? '+' : ''}${pct}%`} title={`было ${nf(prev)}`} />;
}
function deltaPp(cur: number | null, prev: number | null): React.ReactNode {
  if (cur == null || prev == null) return null;
  const d = Math.round((cur - prev) * 10) / 10;
  return <DeltaTag dir={d > 0 ? 'up' : d < 0 ? 'down' : 'flat'} text={`${d > 0 ? '+' : ''}${d} пп`} title={`было ${prev}%`} />;
}

function convBadge(v: number | null): React.ReactNode {
  if (v == null) return '—';
  const tone = v >= 7 ? { bg: '#e9f5ee', c: 'var(--bb-green)' } : v >= 4 ? { bg: '#fdf1e6', c: '#b56a1d' } : { bg: '#fdeaec', c: 'var(--bb-red)' };
  return <span style={{ background: tone.bg, color: tone.c, fontWeight: 700, fontSize: 12, borderRadius: 8, padding: '2px 8px' }}>{v}%</span>;
}

// ───────────────────────── A. KPI обзвона ─────────────────────────

export function TmKpiGrid({ kpis, kpisPrev, cmpLabel }: { kpis: TmKpis; kpisPrev?: TmKpis | null; cmpLabel?: string }) {
  const p = kpisPrev ?? null;
  return (
    <div>
      {p ? (
        <div style={{ fontSize: 12, color: 'var(--bb-faint)', marginBottom: 12 }}>
          ↑↓ — к аналогичному периоду прошлого месяца по календарным дням{cmpLabel ? ` (${cmpLabel})` : ''}
        </div>
      ) : null}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 14 }}>
        <Mini label="Наборов" value={nf(kpis.dials)} sub={`${nf(kpis.dialsPerDay)}/день · ${nf(kpis.dialsPerZvonar)} на телемаркетолога`} delta={p ? deltaCount(kpis.dials, p.dials) : null} />
        <Mini label="Дозвонов ≥60с" value={nf(kpis.calls60)} sub={`${nf(kpis.calls60PerDay)}/день · ${kpis.dials > 0 ? Math.round((kpis.calls60 / kpis.dials) * 100) : 0}% от наборов`} tone="good" delta={p ? deltaCount(kpis.calls60, p.calls60) : null} />
        <Mini label="Берут трубку" value={pp(kpis.answerPct)} sub={`${nf(kpis.answered)} соединений`} delta={p ? deltaPp(kpis.answerPct, p.answerPct) : null} />
        <Mini label="Часы разговоров" value={`${kpis.talkHours} ч`} sub={`телемаркетологов: ${kpis.zvonari}`} delta={p ? deltaCount(kpis.talkHours, p.talkHours) : null} />
      </div>
      <div className="bb-grid bb-grid-4">
        <Mini label="Встреч назначено" value={nf(kpis.meetingsSet)} sub="по создателю (ТМ)" tone="good" delta={p ? deltaCount(kpis.meetingsSet, p.meetingsSet) : null} />
        <Mini label="Встреч состоялось" value={nf(kpis.meetingsHeld)} sub="назначены ТМ, прошли по БП" tone="good" delta={p ? deltaCount(kpis.meetingsHeld, p.meetingsHeld) : null} />
        <Mini label="Явка" value={pp(kpis.heldPct)} sub="состоялось / назначено" delta={p ? deltaPp(kpis.heldPct, p.heldPct) : null} />
        <Mini label="Конверсия дозвон→встреча" value={pp(kpis.convDialToMeeting)} sub={`${nf(kpis.meetingsSet)} / ${nf(kpis.calls60)} дозвонов`} delta={p ? deltaPp(kpis.convDialToMeeting, p.convDialToMeeting) : null} />
      </div>
    </div>
  );
}

// ───────────────────────── B. По звонарям ─────────────────────────

export function TmManagerTable({ rows }: { rows: TmManagerRow[] }) {
  if (rows.length === 0) return <p style={{ color: 'var(--bb-muted)' }}>Нет активности телемаркетинга за период.</p>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr>
            <th style={{ ...head, textAlign: 'left' }}>Телемаркетолог</th>
            <th style={{ ...head, textAlign: 'right' }}>Наборы</th>
            <th style={{ ...head, textAlign: 'right' }}>Снято</th>
            <th style={{ ...head, textAlign: 'right' }}>Дозвон ≥60с</th>
            <th style={{ ...head, textAlign: 'right' }}>Разговор</th>
            <th style={{ ...head, textAlign: 'right' }}>Встреч назн.</th>
            <th style={{ ...head, textAlign: 'right' }}>Состоялось</th>
            <th style={{ ...head, textAlign: 'right' }}>Явка</th>
            <th style={{ ...head, textAlign: 'right' }}>Конв. дозв→встр</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.managerId}>
              <td style={cell}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={ava}>{initials(r.name)}</div>
                  <div>
                    <b>{r.name}</b>
                    {r.dept ? <div style={{ color: 'var(--bb-faint)', fontSize: 11.5 }}>{r.dept}</div> : null}
                  </div>
                </div>
              </td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.dials)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.answered)} <span style={{ color: 'var(--bb-faint)' }}>{pp(r.answerPct)}</span></td>
              <td className="tabular" style={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{nf(r.calls60)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.talkHours} ч</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{nf(r.meetingsSet)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.meetingsHeld)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{pp(r.heldPct)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{convBadge(r.convDialToMeeting)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Дозвон = разговор ≥60 секунд. Встреча «назначено» засчитывается создателю (телемаркетологу).
      </p>
    </div>
  );
}

// ───────────────────────── C. Воронка cat50 ─────────────────────────

// TmFunnel50View вынесен в отдельный клиентский компонент TmFunnel.tsx
// (мультиселект владельцев — ТМ и МП).

// ───────────────────── D. Встречи → результат ─────────────────────

export function TmMeetingsResultView({ result }: { result: TmMeetingsResult }) {
  return (
    <div>
      <div className="bb-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <Mini label="Назначено" value={nf(result.set)} sub="по создателю (ТМ)" tone="good" />
        <Mini label="Состоялось" value={nf(result.held)} sub="прошли по бизнес-процессу" tone="good" />
        <Mini label="Явка" value={pp(result.heldPct)} sub="состоялось / назначено" />
      </div>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Событийная логика: встречу назначил ТМ (создатель) и она состоялась по бизнес-процессу (DT1048:SUCCESS) —
        засчитывается ТМ, даже если проводил продавец. Маркетинговый источник сделки не учитываем (он по первому обращению).
      </p>
    </div>
  );
}

// ───────────────────── F. Динамика по месяцам ─────────────────────

export function TmMonthlyView({ rows, name }: { rows: TmMonthlyRow[]; name: string | null }) {
  if (rows.length === 0) return <p style={{ color: 'var(--bb-muted)' }}>Нет истории по выбранному телемаркетологу.</p>;
  // Обрезаем ведущие месяцы без активности (звонарь ещё не работал).
  const firstActive = rows.findIndex((r) => r.dials > 0 || r.calls60 > 0 || r.meetingsSet > 0);
  const shown = firstActive > 0 ? rows.slice(firstActive) : rows;
  if (shown.every((r) => r.dials === 0 && r.meetingsSet === 0)) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет истории по выбранному телемаркетологу.</p>;
  }
  const maxConv = Math.max(...shown.map((r) => r.conv ?? 0), 1);
  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ ...head, textAlign: 'left' }}>Месяц</th>
              <th style={{ ...head, textAlign: 'right' }}>Набрано</th>
              <th style={{ ...head, textAlign: 'right' }}>Снято</th>
              <th style={{ ...head, textAlign: 'right' }}>Дозвон ≥60с</th>
              <th style={{ ...head, textAlign: 'right' }}>Разговор</th>
              <th style={{ ...head, textAlign: 'right' }}>Встреч назн.</th>
              <th style={{ ...head, textAlign: 'right' }}>Состоялось</th>
              <th style={{ ...head, textAlign: 'right' }}>Конв.</th>
              <th style={{ ...head, textAlign: 'right' }}>Отвал</th>
              <th style={{ ...head, textAlign: 'right' }}>Отлож.</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.ym}>
                <td style={{ ...cell, fontWeight: 600 }}>{r.label}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.dials)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.answered)} <span style={{ color: 'var(--bb-faint)' }}>{pp(r.answerPct)}</span></td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.calls60)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.talkMin)} м</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{nf(r.meetingsSet)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.meetingsHeld)}</td>
                <td style={{ ...cell, textAlign: 'right' }}>{convBadge(r.conv)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right', color: 'var(--bb-muted)' }}>{nf(r.rejected)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right', color: 'var(--bb-faint)' }}>{nf(r.postponed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
          Конверсия «дозвон → встреча», %{name ? ` · ${name}` : ''}
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 120 }}>
          {shown.map((r) => {
            const v = r.conv ?? 0;
            const color = v >= 7 ? 'var(--bb-green)' : v >= 4 ? 'var(--bb-amber)' : 'var(--bb-red)';
            return (
              <div key={r.ym} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%', gap: 6 }}>
                <div style={{ fontSize: 11.5, fontWeight: 700, color }}>{r.conv != null ? r.conv : '—'}</div>
                <div style={{ width: '100%', maxWidth: 38, height: `${Math.max(4, (v / maxConv) * 100)}%`, background: color, borderRadius: '6px 6px 0 0' }} />
                <div style={{ fontSize: 10.5, color: 'var(--bb-faint)' }}>{r.label}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ───────────────────── Микро-воронка звонка ─────────────────────

export function TmMicroFunnelsView({ funnels }: { funnels: TmMicroFunnel[] }) {
  return (
    <div className="bb-grid" style={{ gridTemplateColumns: funnels.length > 1 ? 'repeat(2, 1fr)' : '1fr' }}>
      {funnels.map((f) => (
        <div key={f.managerId} style={{ background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 16, padding: 16, boxShadow: 'var(--bb-shadow)' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>{f.name}</div>
          <div style={{ display: 'flex', alignItems: 'stretch' }}>
            {f.steps.map((s, i) => (
              <div key={s.label} style={{ display: 'contents' }}>
                {i > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '0 6px', minWidth: 44 }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: (s.pctFromPrev ?? 0) >= 50 ? 'var(--bb-green)' : (s.pctFromPrev ?? 0) >= 10 ? 'var(--bb-amber)' : 'var(--bb-red)' }}>{pp(s.pctFromPrev)}</div>
                    <div style={{ fontSize: 14, opacity: 0.4 }}>→</div>
                  </div>
                ) : null}
                <div style={{ flex: 1, textAlign: 'center', padding: '12px 4px', background: '#faf8f5', border: '1px solid var(--bb-line)', borderRadius: 12 }}>
                  <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em' }}>{nf(s.value)}</div>
                  <div style={{ fontSize: 10, color: 'var(--bb-faint)', textTransform: 'uppercase', letterSpacing: '0.03em', marginTop: 3 }}>{s.label}</div>
                </div>
              </div>
            ))}
          </div>
          {f.burn != null ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, padding: '10px 12px', borderRadius: 11, background: '#faf7f2', border: '1px solid var(--bb-line)' }}>
              <div style={{ fontSize: 20, fontWeight: 800, color: f.burn >= 10 ? 'var(--bb-red)' : f.burn >= 6 ? 'var(--bb-amber)' : 'var(--bb-green)' }}>{nf(f.burn)}</div>
              <div style={{ fontSize: 12, color: 'var(--bb-muted)' }}><b>лидов сожжено на 1 встречу</b> (личных отвалов за период / назначенных встреч)</div>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

// ───────────────────────── Причины отвала ─────────────────────────

export function TmRejectionsView({ rejections }: { rejections: TmRejections[] }) {
  if (rejections.length === 0 || rejections.every((r) => r.total === 0)) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет личных отвалов по телемаркетологам (массовые/админ-закрытия исключены).</p>;
  }
  return (
    <div className="bb-grid" style={{ gridTemplateColumns: rejections.length > 1 ? 'repeat(2, 1fr)' : '1fr' }}>
      {rejections.map((r) => {
        const max = Math.max(...r.reasons.map((x) => x.count), 1);
        return (
          <div key={r.managerId} style={{ background: '#fff', border: '1px solid var(--bb-line)', borderRadius: 16, padding: 18, boxShadow: 'var(--bb-shadow)' }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>
              {r.name} <span style={{ color: 'var(--bb-faint)', fontWeight: 500 }}>· {nf(r.total)} отвалов</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {r.reasons.slice(0, 7).map((b, i) => (
                <div key={`${b.reasonId}`} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 78px', alignItems: 'center', gap: 10 }}>
                  <div style={{ fontSize: 12.5 }}>{b.label}</div>
                  <div style={{ height: 18, background: '#f3f0ec', borderRadius: 6, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.max(3, (b.count / max) * 100)}%`, borderRadius: 6, background: i < 2 ? 'linear-gradient(90deg,#e0606b,#d4202e)' : 'linear-gradient(90deg,#cfcbf2,#8b80ff)' }} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--bb-muted)', textAlign: 'right' }}>
                    <b style={{ color: 'var(--bb-ink)' }}>{nf(b.count)}</b> · {b.pct}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ───────────────────────── E. План / факт ─────────────────────────

function pfPct(f: number, p: number): number | null {
  return p > 0 ? Math.round((f / p) * 100) : null;
}
function pfTone(p: number | null): 'green' | 'amber' | 'red' | 'grey' {
  return p == null ? 'grey' : p >= 100 ? 'green' : p >= 50 ? 'amber' : 'red';
}
const PF_PILL: Record<string, React.CSSProperties> = {
  green: { background: '#e7f4ec', color: 'var(--bb-green)' },
  amber: { background: '#fdf2e7', color: '#b5651d' },
  red: { background: '#fdeced', color: 'var(--bb-red)' },
  grey: { background: '#eef0f4', color: 'var(--bb-muted)' },
};
const PF_FILL: Record<string, string> = {
  green: 'linear-gradient(90deg,#5fcf8b,#2c7a4a)',
  amber: 'linear-gradient(90deg,#f4b46a,#e88a3b)',
  red: 'linear-gradient(90deg,#ef8d5e,#d4202e)',
  grey: '#dcd7d0',
};
function pfInitials(name: string): string {
  const x = name.trim().split(/\s+/);
  return ((x[0]?.[0] ?? '') + (x[1]?.[0] ?? '')).toUpperCase() || '—';
}

function PfRow({ ava, name, fact, plan, team }: { ava: string; name: string; fact: number; plan: number; team?: boolean }) {
  const p = pfPct(fact, plan);
  const tone = pfTone(p);
  const fill = p == null || p === 0 ? 2 : Math.min(100, p);
  return (
    <div style={{
      padding: team ? '9px 12px' : '8px 0',
      margin: team ? '5px -12px 0' : undefined,
      background: team ? 'linear-gradient(90deg,var(--bb-violet-soft),transparent)' : undefined,
      borderRadius: team ? 11 : undefined,
      borderTop: team ? undefined : '1px solid #f4f1ec',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ width: 24, height: 24, flex: '0 0 24px', borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: 9.5, fontWeight: 700, color: '#fff', background: team ? 'linear-gradient(135deg,var(--bb-indigo),var(--bb-violet))' : 'linear-gradient(135deg,#8b80ff,#5b50d6)' }}>{ava}</span>
        <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
        <span className="tabular" style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
          <b style={{ fontWeight: 800 }}>{nf(fact)}</b> <span style={{ color: 'var(--bb-faint)', fontWeight: 600 }}>/ {nf(plan)}</span>
        </span>
        <span className="tabular" style={{ ...PF_PILL[tone], fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '2px 9px', flex: '0 0 auto' }}>{p != null ? `${p}%` : '—'}</span>
      </div>
      <div style={{ height: 6, borderRadius: 5, background: '#f1ede8', overflow: 'hidden' }}>
        <i style={{ display: 'block', height: '100%', borderRadius: 5, width: `${fill}%`, background: p ? PF_FILL[tone] : PF_FILL.grey }} />
      </div>
    </div>
  );
}

function PfHead({ dot, title, hint }: { dot: string; title: string; hint: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot, flex: '0 0 auto' }} />
      <h4 style={{ fontSize: 13, fontWeight: 800, margin: 0 }}>{title}</h4>
      <span style={{ fontSize: 11, color: 'var(--bb-faint)', marginLeft: 'auto', fontWeight: 500 }}>{hint}</span>
    </div>
  );
}

export function TmPlanFactView({ data }: { data: TmPlanFact }) {
  if (data.dials60.managers.length === 0) return <p style={{ color: 'var(--bb-muted)' }}>Телемаркетологи за период не найдены.</p>;
  return (
    <div className="bb-pf-cols" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
      <div style={{ paddingRight: 26, borderRight: '1px solid var(--bb-line)' }}>
        <PfHead dot="var(--bb-violet)" title="Дозвоны ≥60с" hint={`план ${data.dials60.perTm}/чел`} />
        {data.dials60.managers.map((m) => (
          <PfRow key={`d-${m.managerId}`} ava={pfInitials(m.name)} name={m.name} fact={m.fact} plan={m.plan} />
        ))}
        <PfRow ava="ТМ" name="Итого" fact={data.dials60.teamFact} plan={data.dials60.teamPlan} team />
      </div>
      <div style={{ paddingLeft: 26 }}>
        <PfHead dot="var(--bb-green)" title="Брифования состоялись" hint={`план ${data.briefings.perTm}/чел`} />
        {data.briefings.managers.map((m) => (
          <PfRow key={`b-${m.managerId}`} ava={pfInitials(m.name)} name={m.name} fact={m.fact} plan={m.plan} />
        ))}
        <PfRow ava="ТМ" name="Итого" fact={data.briefings.teamFact} plan={data.briefings.teamPlan} team />
      </div>
    </div>
  );
}

// ───────────────────────── G. Outreach ─────────────────────────

export function TmOutreachView({ outreach }: { outreach: TmOutreach }) {
  if (outreach.rows.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет email/мессенджер-активности у ТМ.</p>;
  }
  return (
    <div className="bb-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
      <Mini label="Мессенджер-диалоги" value={nf(outreach.messengerTotal)} />
      <Mini label="Email-касания" value={nf(outreach.emailTotal)} />
      <Mini label="Касаний на встречу" value={outreach.perMeeting != null ? nf(outreach.perMeeting) : '—'} sub="доп. канал к телефону" />
    </div>
  );
}


// ───────────────────────── Heatmap времени дозвона ─────────────────────────

export function TmHeatmapView({ heatmap }: { heatmap: TmHeatmap }) {
  if (heatmap.hours.length === 0 || heatmap.rows.every((r) => r.cells.every((c) => c.pct == null))) {
    return <p style={{ color: 'var(--bb-muted)' }}>Недостаточно данных о звонках для тепловой карты.</p>;
  }
  const { mean, minSample } = heatmap;
  // Максимум объёма среди достоверных ячеек — для нормировки яркости.
  const maxDials = Math.max(
    1,
    ...heatmap.rows.flatMap((r) => r.cells.filter((c) => c.dials >= minSample).map((c) => c.dials)),
  );
  // Цвет = отклонение от среднего (синий ниже · зелёный выше); текст тёмный, кроме
  // сильного зелёного. Якорь — среднее по отделу.
  const devColor = (pct: number): { bg: string; fg: string } => {
    const dev = pct - mean;
    if (dev <= -8) return { bg: '#a9bce6', fg: '#27314a' };
    if (dev <= -3) return { bg: '#cdd8ef', fg: '#2c2a3e' };
    if (dev < 3) return { bg: '#e4ddcf', fg: '#2c2a3e' };
    if (dev < 8) return { bg: '#bfe3cd', fg: '#1e4a32' };
    return { bg: '#3a9c63', fg: '#fff' };
  };
  const cols = `34px repeat(${heatmap.hours.length}, minmax(48px, 1fr))`;
  const legend: { box: React.CSSProperties; label: string }[] = [
    { box: { background: '#a9bce6' }, label: 'заметно ниже' },
    { box: { background: '#cdd8ef' }, label: 'ниже' },
    { box: { background: '#e4ddcf' }, label: '~среднее' },
    { box: { background: '#bfe3cd' }, label: 'выше' },
    { box: { background: '#3a9c63' }, label: 'заметно выше' },
    { box: { background: '#efece6', border: '1px dashed #cfcabf' }, label: 'мало данных' },
  ];
  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 5, minWidth: 760 }}>
          <div />
          {heatmap.hours.map((h) => (
            <div key={`h${h}`} style={{ textAlign: 'center', fontSize: 11.5, color: 'var(--bb-faint)', fontWeight: 700, paddingBottom: 2 }}>{h}</div>
          ))}
          {heatmap.rows.map((row) => (
            <div key={`r${row.dow}`} style={{ display: 'contents' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', fontSize: 12.5, color: 'var(--bb-muted)', fontWeight: 700, paddingRight: 4 }}>{row.label}</div>
              {row.cells.map((c) => {
                if (c.pct == null) {
                  // нет звонков в этот час
                  return <div key={`${row.dow}-${c.hour}`} style={{ height: 40, borderRadius: 9 }} />;
                }
                if (c.dials < minSample) {
                  return (
                    <div key={`${row.dow}-${c.hour}`}
                      title={`${row.label} ${c.hour}:00 — мало данных (${nf(c.dials)} наборов)`}
                      style={{ height: 40, borderRadius: 9, background: '#efece6', border: '1px dashed #cfcabf', display: 'grid', placeItems: 'center', color: '#b7b2a6', fontSize: 9, fontWeight: 700, lineHeight: 1.1, textAlign: 'center' }}>
                      мало<br />данных
                    </div>
                  );
                }
                const { bg, fg } = devColor(c.pct);
                const opacity = Math.min(1, 0.5 + (c.dials / maxDials) * 0.5);
                return (
                  <div key={`${row.dow}-${c.hour}`}
                    title={`${row.label} ${c.hour}:00 — дозвон ${c.pct}% (${nf(c.calls60)}/${nf(c.dials)} наборов) · среднее ${mean}%`}
                    style={{ position: 'relative', height: 40, borderRadius: 9, background: bg, opacity, display: 'grid', placeItems: 'center', color: fg, fontSize: 12.5, fontWeight: 800 }}>
                    <span className="tabular">{c.pct}%</span>
                    <span className="tabular" style={{ position: 'absolute', bottom: 2, right: 5, fontSize: 8.5, fontWeight: 700, opacity: 0.75 }}>{nf(c.dials)}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center', marginTop: 14, fontSize: 12, color: 'var(--bb-muted)' }}>
        {legend.map((l) => (
          <span key={l.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 16, height: 16, borderRadius: 5, display: 'inline-block', ...l.box }} />
            {l.label}
          </span>
        ))}
      </div>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        % дозвона ≥60с по часам (МСК) и дням недели за 3 месяца · цвет — отклонение от среднего по отделу ({mean}%), число снизу — объём наборов · ячейки с выборкой меньше {minSample} наборов помечены «мало данных». Дозвон = разговор ≥60 секунд.
      </p>
    </div>
  );
}

// ───────────────── Качество встреч ТМ (из разбора) ─────────────────

export function TmMeetingQualityView({ quality }: { quality: TmMeetingQuality }) {
  if (quality.total === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет разобранных встреч, назначенных ТМ, за период.</p>;
  }
  return (
    <div>
      <div style={{ fontSize: 13, color: 'var(--bb-muted)', marginBottom: 8 }}>
        {nf(quality.total)} разобранных встреч от ТМ (из разбора на «Анализе встреч»):
      </div>
      <div style={{ height: 28, borderRadius: 9, overflow: 'hidden', display: 'flex' }}>
        {quality.rich > 0 ? <div style={{ flex: quality.rich, background: 'linear-gradient(90deg,#3a9c63,#2c7a4a)', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700 }}>содержательные {quality.richPct}%</div> : null}
        {quality.weak > 0 ? <div style={{ flex: quality.weak, background: 'var(--bb-amber)', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700 }}>слабые {quality.weakPct}%</div> : null}
        {quality.empty > 0 ? <div style={{ flex: quality.empty, background: '#c9c5d2', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700 }}>пустые {quality.emptyPct}%</div> : null}
      </div>
      <div className="bb-grid bb-grid-4" style={{ marginTop: 14 }}>
        <Mini label="Содержательные" value={`${quality.richPct}%`} sub="балл ≥7" tone="good" />
        <Mini label="Пустые" value={nf(quality.empty)} sub="балл <4 · разобрать с РОПом" tone="warn" />
        <Mini label="Со след. шагом" value={quality.nextStepPct != null ? `${quality.nextStepPct}%` : '—'} />
        <Mini label="Разобрано" value={nf(quality.total)} sub={quality.byManager.map((m) => `${m.name.split(' ')[0]} ${m.richPct}%`).join(' · ')} />
      </div>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        «Пустая» = встреча с низким баллом разбора (без выявленной потребности/бюджета/след. шага). Балл — из готового разбора на странице «Анализ встреч».
      </p>
    </div>
  );
}

// ───────────────────────── ТМ-алерты ─────────────────────────

export function TmAlertsView({ alerts }: { alerts: TmAlert[] }) {
  if (alerts.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Сигналов нет — конверсия и явка в норме.</p>;
  }
  const tone = (l: TmAlert['level']) =>
    l === 'red' ? { bg: '#fdeaec', c: 'var(--bb-red)' } : l === 'green' ? { bg: '#e9f5ee', c: 'var(--bb-green)' } : { bg: '#fdf1e6', c: '#b56a1d' };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {alerts.map((a, i) => {
        const t = tone(a.level);
        return (
          <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '12px 14px', borderRadius: 12, border: '1px solid var(--bb-line)', background: '#fff' }}>
            <div style={{ width: 30, height: 30, borderRadius: 9, display: 'grid', placeItems: 'center', flex: '0 0 30px', background: t.bg, color: t.c, fontSize: 15 }}>{a.icon}</div>
            <div>
              <b style={{ fontSize: 13.5 }}>{a.title}</b>
              <p style={{ margin: '2px 0 0', fontSize: 12.5, color: 'var(--bb-muted)' }}>{a.text}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ───────────────── Карточка «скоро» (рунер-зависимые блоки) ─────────────────

export function SoonCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div style={{ border: '1px dashed var(--bb-line)', borderRadius: 16, padding: '16px 18px', background: '#faf8f5', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <span style={{ fontSize: 10.5, fontWeight: 700, color: '#b56a1d', background: '#fdf3e7', border: '1px solid #f3dcbd', borderRadius: 8, padding: '2px 8px', whiteSpace: 'nowrap', marginTop: 2 }}>скоро</span>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{title}</div>
        <div style={{ fontSize: 12.5, color: 'var(--bb-muted)', marginTop: 2 }}>{desc}</div>
      </div>
    </div>
  );
}
