import Link from 'next/link';
import type {
  TmFunnel50Stage,
  TmKpis,
  TmManagerRow,
  TmManagerOption,
  TmMeetingsResult,
  TmMicroFunnel,
  TmMonthlyRow,
  TmOutreach,
  TmPlanFactRow,
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

function Mini({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'good' | 'warn' }) {
  const bg = tone === 'good' ? 'linear-gradient(180deg,#f4faf6,#fff)' : tone === 'warn' ? 'linear-gradient(180deg,#fdf4ee,#fff)' : '#fff';
  return (
    <div style={{ background: bg, border: '1px solid var(--bb-line)', borderRadius: 16, padding: '15px 17px', boxShadow: 'var(--bb-shadow)' }}>
      <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.05 }}>{value}</div>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 6 }}>{label}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 3 }}>{sub}</div> : null}
    </div>
  );
}

function convBadge(v: number | null): React.ReactNode {
  if (v == null) return '—';
  const tone = v >= 7 ? { bg: '#e9f5ee', c: 'var(--bb-green)' } : v >= 4 ? { bg: '#fdf1e6', c: '#b56a1d' } : { bg: '#fdeaec', c: 'var(--bb-red)' };
  return <span style={{ background: tone.bg, color: tone.c, fontWeight: 700, fontSize: 12, borderRadius: 8, padding: '2px 8px' }}>{v}%</span>;
}

// ───────────────────────── A. KPI обзвона ─────────────────────────

export function TmKpiGrid({ kpis }: { kpis: TmKpis }) {
  return (
    <div>
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 14 }}>
        <Mini label="Наборов" value={nf(kpis.dials)} sub={`${nf(kpis.dialsPerDay)}/день · ${nf(kpis.dialsPerZvonar)} на звонаря`} />
        <Mini label="Дозвонов ≥60с" value={nf(kpis.calls60)} sub={`${nf(kpis.calls60PerDay)}/день · ${kpis.dials > 0 ? Math.round((kpis.calls60 / kpis.dials) * 100) : 0}% от наборов`} tone="good" />
        <Mini label="Берут трубку" value={pp(kpis.answerPct)} sub={`${nf(kpis.answered)} соединений`} />
        <Mini label="Часы разговоров" value={`${kpis.talkHours} ч`} sub={`звонарей: ${kpis.zvonari}`} />
      </div>
      <div className="bb-grid bb-grid-4">
        <Mini label="Встреч назначено" value={nf(kpis.meetingsSet)} sub="по создателю (ТМ)" tone="good" />
        <Mini label="Конверсия дозвон→встреча" value={pp(kpis.convDialToMeeting)} sub={`${nf(kpis.meetingsSet)} / ${nf(kpis.calls60)} дозвонов`} />
        <Mini label="Встреч проведено" value={nf(kpis.meetingsHeld)} />
        <Mini label="Передано в Продажи" value={nf(kpis.toCold)} sub="холод · cat50 → cat10" />
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
            <th style={{ ...head, textAlign: 'left' }}>Звонарь</th>
            <th style={{ ...head, textAlign: 'right' }}>Наборы</th>
            <th style={{ ...head, textAlign: 'right' }}>Снято</th>
            <th style={{ ...head, textAlign: 'right' }}>Дозвон ≥60с</th>
            <th style={{ ...head, textAlign: 'right' }}>Разговор</th>
            <th style={{ ...head, textAlign: 'right' }}>Встреч назн.</th>
            <th style={{ ...head, textAlign: 'right' }}>Конв. дозв→встр</th>
            <th style={{ ...head, textAlign: 'right' }}>Явка</th>
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
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{convBadge(r.convDialToMeeting)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{pp(r.heldPct)}</td>
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

export function TmFunnel50View({ stages }: { stages: TmFunnel50Stage[] }) {
  const max = Math.max(...stages.map((s) => s.count), 1);
  const fill = (kind: TmFunnel50Stage['kind']) =>
    kind === 'win'
      ? 'linear-gradient(90deg,#3a9c63,#2c7a4a)'
      : kind === 'lose'
        ? 'linear-gradient(90deg,#e0606b,#d4202e)'
        : 'linear-gradient(90deg,var(--bb-violet),var(--bb-indigo))';
  if (stages.every((s) => s.count === 0)) {
    return <p style={{ color: 'var(--bb-muted)' }}>Снимок воронки [50] пуст на последнюю дату.</p>;
  }
  // Закрытые стадии (Успех/Отложено/Отвал) в снимок открытых сделок не попадают —
  // показываем их только если есть данные; иначе скрываем, чтобы не висели нулём.
  const shown = stages.filter((s) => s.kind === 'open' || s.count > 0);
  return (
    <div>
      <div className="bb-funnel">
        {shown.map((s) => (
          <div className="bb-fbar" key={s.stage}>
            <span className="bb-fbar-name">{s.label}</span>
            <div className="bb-fbar-track">
              <div className="bb-fbar-fill" style={{ width: `${Math.max(8, (s.count / max) * 100)}%`, background: fill(s.kind) }}>
                {nf(s.count)}
              </div>
            </div>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Снимок открытых сделок cat50. «Успех / Отвал за месяц» (закрытые) и Δ к началу месяца — со сбором потока в раннере.
      </p>
    </div>
  );
}

// ───────────────────── D. Встречи → результат ─────────────────────

export function TmMeetingsResultView({ result }: { result: TmMeetingsResult }) {
  return (
    <div>
      <div className="bb-grid bb-grid-4">
        <Mini label="Назначено" value={nf(result.set)} />
        <Mini label="Проведено" value={nf(result.held)} tone="good" />
        <Mini label="Явка (провед/назн)" value={pp(result.heldPct)} />
        <Mini label="В Продажи (холод)" value={nf(result.toCold)} />
      </div>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Назначенная встреча — создателю (ТМ), проведённая — ответственному (продавцу). «В Продажи» = сделка переведена из ТМ-воронки в воронку Продажи (cat10).
      </p>
    </div>
  );
}

// ───────────────────── F. Динамика по месяцам ─────────────────────

export function TmMonthlyView({ rows, name }: { rows: TmMonthlyRow[]; name: string | null }) {
  if (rows.length === 0) return <p style={{ color: 'var(--bb-muted)' }}>Нет истории по выбранному звонарю.</p>;
  const maxConv = Math.max(...rows.map((r) => r.conv ?? 0), 1);
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
              <th style={{ ...head, textAlign: 'right' }}>Встреч</th>
              <th style={{ ...head, textAlign: 'right' }}>Провед.</th>
              <th style={{ ...head, textAlign: 'right' }}>Конв.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ym}>
                <td style={{ ...cell, fontWeight: 600 }}>{r.label}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.dials)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.answered)} <span style={{ color: 'var(--bb-faint)' }}>{pp(r.answerPct)}</span></td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.calls60)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.talkMin)} м</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{nf(r.meetingsSet)}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{nf(r.meetingsHeld)}</td>
                <td style={{ ...cell, textAlign: 'right' }}>{convBadge(r.conv)}</td>
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
          {rows.map((r) => {
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
        </div>
      ))}
    </div>
  );
}

// ───────────────────────── E. План / факт ─────────────────────────

export function TmPlanFactView({ rows }: { rows: TmPlanFactRow[] }) {
  if (rows.length === 0) return <p style={{ color: 'var(--bb-muted)' }}>План на период не задан.</p>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {rows.map((r) => {
        const over = r.pct >= 100;
        const bar = over ? 'linear-gradient(90deg,#3a9c63,#2c7a4a)' : r.pct >= 80 ? 'linear-gradient(90deg,var(--bb-violet),var(--bb-indigo))' : 'linear-gradient(90deg,#e88a3b,#d4202e)';
        return (
          <div key={r.label}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6, gap: 12 }}>
              <span>{r.label} {r.unit ? <span style={{ color: 'var(--bb-faint)', fontSize: 11.5 }}>· {r.unit}</span> : null}</span>
              <b style={{ whiteSpace: 'nowrap' }}>
                {r.isPercent ? `${nf(r.fact)}% / ${nf(r.plan)}%` : `${nf(r.fact)} / ${nf(r.plan)}`}{' '}
                <span style={{ color: over ? 'var(--bb-green)' : 'var(--bb-muted)' }}>({r.pct}%)</span>
              </b>
            </div>
            <div style={{ height: 10, borderRadius: 6, background: '#f0ece7', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.min(100, r.pct)}%`, background: bar }} />
            </div>
          </div>
        );
      })}
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

// ───────────────── Селектор звонаря (через ?manager) ─────────────────

export function TmManagerSelect({
  managers,
  selectedId,
  range,
}: {
  managers: TmManagerOption[];
  selectedId: number | null;
  range: 'month' | 'week';
}) {
  if (managers.length <= 1) return null;
  const q = (id: number) => `/telemarketing?period=${range}&manager=${id}`;
  return (
    <div style={{ display: 'inline-flex', gap: 4, background: '#f3f0ec', borderRadius: 10, padding: 3, marginLeft: 'auto', flexWrap: 'wrap' }}>
      <span style={{ alignSelf: 'center', color: 'var(--bb-faint)', fontWeight: 600, fontSize: 12.5, padding: '0 6px' }}>Звонарь:</span>
      {managers.map((m) => {
        const on = m.managerId === selectedId;
        return (
          <Link
            key={m.managerId}
            href={q(m.managerId)}
            style={{
              padding: '5px 12px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, textDecoration: 'none',
              background: on ? '#fff' : 'transparent', color: on ? 'var(--bb-violet)' : 'var(--bb-muted)',
              boxShadow: on ? '0 1px 2px rgba(0,0,0,.05)' : 'none',
            }}
          >
            {m.name}
          </Link>
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
