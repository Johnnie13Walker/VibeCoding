import type { Forecast, PlanFact } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн ₽`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс ₽`;
  return `${Math.round(v)} ₽`;
}
/** Короткий формат для строк воронки: «2.55 млн» / «383 тыс» / «0 ₽». */
function short(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)} ₽`;
}
function num(v: number, fmtMoney: boolean): string {
  if (!fmtMoney) return `${v}`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)}`;
}
const pct = (f: number, p: number): number | null => (p > 0 ? Math.round((f / p) * 100) : null);

type Tone = 'green' | 'amber' | 'red' | 'grey';
const toneByPct = (p: number | null): Tone => (p == null ? 'grey' : p >= 100 ? 'green' : p >= 50 ? 'amber' : 'red');
const PILL: Record<Tone, React.CSSProperties> = {
  green: { background: '#e7f4ec', color: 'var(--bb-green)' },
  amber: { background: '#fdf2e7', color: '#b5651d' },
  red: { background: '#fdeced', color: 'var(--bb-red)' },
  grey: { background: '#eef0f4', color: 'var(--bb-muted)' },
};
const BAR_FILL: Record<Tone, string> = {
  green: 'linear-gradient(90deg,#5fcf8b,#2c7a4a)',
  amber: 'linear-gradient(90deg,#f4b46a,#e88a3b)',
  red: 'linear-gradient(90deg,#ef8d5e,#d4202e)',
  grey: '#dcd7d0',
};

function Pill({ p }: { p: number | null }) {
  return (
    <span className="tabular" style={{ ...PILL[toneByPct(p)], fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '2px 9px', lineHeight: 1.5, flex: '0 0 auto' }}>
      {p != null ? `${p}%` : '—'}
    </span>
  );
}

function initials(name: string): string {
  const x = name.trim().split(/\s+/);
  return ((x[0]?.[0] ?? '') + (x[1]?.[0] ?? '')).toUpperCase() || '—';
}

// ── читаемый заголовок секции: точка + тёмный текст ───────────────────────────
function Sh({ dot, title, hint }: { dot: string; title: string; hint?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot, flex: '0 0 auto' }} />
      <h4 style={{ fontSize: 13, fontWeight: 800, margin: 0 }}>{title}</h4>
      {hint ? <span style={{ fontSize: 11, color: 'var(--bb-faint)', marginLeft: 'auto', fontWeight: 500 }}>{hint}</span> : null}
    </div>
  );
}

// ── тонированная плитка прогноза ──────────────────────────────────────────────
const TILE: Record<string, { bg: string; bd: string; lc: string; vc: string }> = {
  violet: { bg: '#f1eefe', bd: '#e2dbfb', lc: '#6f63d6', vc: '#3a2fae' },
  slate: { bg: '#eef1f6', bd: '#e2e7ef', lc: '#7d869b', vc: '#3a4356' },
  green: { bg: '#e9f6ee', bd: '#cdead8', lc: '#3f9b63', vc: 'var(--bb-green)' },
  amber: { bg: '#fdf4e9', bd: '#f3e0c4', lc: '#b5651d', vc: '#b5651d' },
  red: { bg: '#fdecec', bd: '#f7d4d4', lc: '#cf5a5a', vc: 'var(--bb-red)' },
};
function Tile({ tint, label, value, sub }: { tint: keyof typeof TILE; label: string; value: string; sub: string }) {
  const t = TILE[tint];
  return (
    <div style={{ padding: '13px 15px', borderRadius: 14, background: t.bg, border: `1px solid ${t.bd}` }}>
      <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em', fontWeight: 700, color: t.lc, marginBottom: 5 }}>{label}</div>
      <div className="tabular" style={{ fontSize: 19, fontWeight: 800, letterSpacing: '-.025em', lineHeight: 1, color: t.vc }}>{value}</div>
      <div style={{ fontSize: 11, marginTop: 5, color: 'var(--bb-muted)' }}>{sub}</div>
    </div>
  );
}

// ── строка план/факт (оплаты, брифы) ──────────────────────────────────────────
function Row({
  ava, name, role, fact, plan, fmtMoney, team,
}: {
  ava: string; name: string; role?: string; fact: number; plan: number; fmtMoney: boolean; team?: 'v' | 'a';
}) {
  const p = pct(fact, plan);
  const tone = toneByPct(p);
  const teamBg = team === 'v' ? 'linear-gradient(90deg,var(--bb-violet-soft),transparent)'
    : team === 'a' ? 'linear-gradient(90deg,#fdf2e7,transparent)' : undefined;
  const fillWidth = p == null || p === 0 ? 2 : Math.min(100, p);
  return (
    <div style={{
      padding: team ? '10px 12px' : '9px 0',
      margin: team ? '5px -12px 0' : undefined,
      background: teamBg,
      borderRadius: team ? 11 : undefined,
      borderTop: team ? undefined : '1px solid #f4f1ec',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
        <span className="bb-mrow-ava" style={{ width: 24, height: 24, flex: '0 0 24px', fontSize: 9.5, background: team ? 'linear-gradient(135deg,var(--bb-indigo),var(--bb-violet))' : undefined }}>{ava}</span>
        <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {name}{role ? <small style={{ color: 'var(--bb-faint)', fontWeight: 500 }}> · {role}</small> : null}
        </span>
        <span className="tabular" style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
          <b style={{ fontWeight: 800 }}>{num(fact, fmtMoney)}</b> <span style={{ color: 'var(--bb-faint)', fontWeight: 600 }}>/ {plan > 0 ? num(plan, fmtMoney) : '—'}</span>
        </span>
        <Pill p={p} />
      </div>
      <div style={{ height: 6, borderRadius: 5, background: '#f1ede8', overflow: 'hidden' }}>
        <i style={{ display: 'block', height: '100%', borderRadius: 5, width: `${fillWidth}%`, background: p ? BAR_FILL[tone] : BAR_FILL.grey }} />
      </div>
    </div>
  );
}

// ── строка воронки ────────────────────────────────────────────────────────────
function FunnelRow({ label, amount, prob, weighted, maxW }: { label: string; amount: number; prob: number; weighted: number; maxW: number }) {
  const zero = weighted <= 0;
  const w = maxW > 0 ? Math.round((weighted / maxW) * 100) : 0;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '3px 12px', alignItems: 'center', padding: '7px 0', borderTop: '1px solid #f4f1ec' }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: zero ? 'var(--bb-faint)' : 'var(--bb-ink)' }}>{label}</span>
      <span className="tabular" style={{ justifySelf: 'end', fontSize: 12, color: 'var(--bb-muted)', fontWeight: 600, whiteSpace: 'nowrap' }}>
        {short(amount)} · {Math.round(prob * 100)}% → <b style={{ color: 'var(--bb-ink)', fontWeight: 800 }}>{short(weighted)}</b>
      </span>
      <div style={{ gridColumn: '1 / -1', height: 6, borderRadius: 5, background: '#f1ede8', overflow: 'hidden' }}>
        <i style={{ display: 'block', height: '100%', borderRadius: 5, width: `${zero ? 2 : Math.max(4, w)}%`, background: zero ? '#dcd7d0' : 'linear-gradient(90deg,#5fcf8b,#2c7a4a)' }} />
      </div>
    </div>
  );
}

export function PlanFactView({ forecast, data }: { forecast: Forecast; data: PlanFact }) {
  const briefsMop = data.managers[0]?.briefsPlan ?? 0;
  const planTone = toneByPct(forecast.pct);
  const paceTone = toneByPct(forecast.pacePct);
  const paceSub = forecast.paceExpected > 0 ? `${short(forecast.paid)} / ${short(forecast.paceExpected)}` : '—';
  const planSub = forecast.pct == null ? 'нет плана' : forecast.pct >= 100 ? 'с запасом' : forecast.pct >= 50 ? 'ниже плана' : 'риск';
  const maxW = Math.max(...forecast.byStage.map((s) => s.weighted), 1);

  return (
    <div>
      {/* Прогноз — тонированные плитки */}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 20 }}>
        <Tile tint="violet" label="Прогноз закрытия" value={money(forecast.forecastClose)} sub="оплаты + воронка" />
        <Tile tint="slate" label="План отдела" value={forecast.planRevenue > 0 ? money(forecast.planRevenue) : '—'} sub="командный" />
        <Tile tint={planTone === 'grey' ? 'slate' : planTone} label="Прогноз к плану" value={forecast.pct != null ? `${forecast.pct}%` : '—'} sub={planSub} />
        <Tile tint={paceTone === 'grey' ? 'slate' : paceTone} label="Темп (pacing)" value={forecast.pacePct != null ? `${forecast.pacePct}%` : '—'} sub={paceSub} />
      </div>

      {/* Две колонки: оплаты | брифы */}
      <div className="bb-pf-cols" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
        <div style={{ paddingRight: 26, borderRight: '1px solid var(--bb-line)' }}>
          <Sh dot="var(--bb-violet)" title="Оплаты, ₽" hint="командный + индивидуальные" />
          <Row ava="ОП" name="Команда" role="отдел" fact={data.revenueTeamFact} plan={data.revenueTeamPlan} fmtMoney team="v" />
          {data.managers.map((m) => (
            <Row key={`rev-${m.managerId}`} ava={initials(m.name)} name={m.name} fact={m.revenueFact} plan={m.revenuePlan} fmtMoney />
          ))}
        </div>
        <div style={{ paddingLeft: 26 }}>
          <Sh dot="var(--bb-amber)" title="Брифы" hint={briefsMop > 0 ? `план ${briefsMop} на каждого` : undefined} />
          {[...data.managers].sort((a, b) => b.briefsFact - a.briefsFact).map((m) => (
            <Row key={`br-${m.managerId}`} ava={initials(m.name)} name={m.name} fact={m.briefsFact} plan={m.briefsPlan} fmtMoney={false} />
          ))}
          <Row ava="ОП" name="Итого по МОП" fact={data.briefsTeamFact} plan={data.briefsTeamPlan} fmtMoney={false} team="a" />
        </div>
      </div>

      {/* Воронка · прогноз — снизу вверх (ранние стадии сверху → договор снизу) */}
      <div style={{ height: 1, background: 'var(--bb-line)', margin: '18px 0 16px' }} />
      <Sh dot="var(--bb-green)" title="Воронка · прогноз" hint="взвешенно по стадиям · снизу вверх" />
      {forecast.byStage.map((s) => (
        <FunnelRow key={s.label} label={s.label} amount={s.amount} prob={s.prob} weighted={s.weighted} maxW={maxW} />
      ))}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', marginTop: 4, paddingTop: 11, borderTop: '2px solid var(--bb-line)' }}>
        <span style={{ fontSize: 13, fontWeight: 800 }}>Взвешенная воронка</span>
        <span className="tabular" style={{ justifySelf: 'end', fontSize: 14, fontWeight: 800, color: 'var(--bb-violet)' }}>{money(forecast.weighted)}</span>
      </div>
    </div>
  );
}
