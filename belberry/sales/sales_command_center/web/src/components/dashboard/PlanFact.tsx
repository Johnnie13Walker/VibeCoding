import type { Forecast, PlanFact } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн ₽`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс ₽`;
  return `${Math.round(v)} ₽`;
}
function num(v: number, fmtMoney: boolean): string {
  if (!fmtMoney) return `${v}`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)}`;
}
const pct = (f: number, p: number): number | null => (p > 0 ? Math.round((f / p) * 100) : null);

// ── тон по проценту выполнения ────────────────────────────────────────────────
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

// ── строка план/факт ──────────────────────────────────────────────────────────
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

function ColTag({ text, tone }: { text: string; tone: 'v' | 'a' }) {
  const bg = tone === 'v' ? 'var(--bb-violet)' : 'linear-gradient(135deg,#f4b46a,var(--bb-amber))';
  return <span style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.05em', borderRadius: 8, padding: '4px 9px', background: bg, color: '#fff' }}>{text}</span>;
}

export function PlanFactView({ forecast, data }: { forecast: Forecast; data: PlanFact }) {
  const briefsMop = data.managers[0]?.briefsPlan ?? 0;
  const planTone = toneByPct(forecast.pct);
  const paceTone = toneByPct(forecast.pacePct);
  const planSub = forecast.pct == null ? 'нет плана' : forecast.pct >= 100 ? 'с запасом' : forecast.pct >= 50 ? 'ниже плана' : 'риск';
  const paceSub = forecast.pacePct == null ? '—' : forecast.pacePct >= 100 ? 'в темпе' : forecast.pacePct >= 50 ? 'догоняем' : 'отстаём';

  return (
    <div>
      {/* Прогноз — тонированные плитки */}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 22 }}>
        <Tile tint="violet" label="Прогноз закрытия" value={money(forecast.forecastClose)} sub="оплаты + воронка" />
        <Tile tint="slate" label="План отдела" value={forecast.planRevenue > 0 ? money(forecast.planRevenue) : '—'} sub="командный" />
        <Tile tint={planTone === 'grey' ? 'slate' : planTone} label="Прогноз к плану" value={forecast.pct != null ? `${forecast.pct}%` : '—'} sub={planSub} />
        <Tile tint={paceTone === 'grey' ? 'slate' : paceTone} label="Темп (pacing)" value={forecast.pacePct != null ? `${forecast.pacePct}%` : '—'} sub={paceSub} />
      </div>

      {/* Две колонки: оплаты | брифы */}
      <div className="bb-pf-cols" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
        <div style={{ paddingRight: 26, borderRight: '1px solid var(--bb-line)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <ColTag text="Оплаты ₽" tone="v" />
            <span style={{ fontSize: 11, color: 'var(--bb-faint)', marginLeft: 'auto', fontWeight: 500 }}>командный + индивидуальные</span>
          </div>
          <Row ava="ОП" name="Команда" role="отдел" fact={data.revenueTeamFact} plan={data.revenueTeamPlan} fmtMoney team="v" />
          {data.managers.map((m) => (
            <Row key={`rev-${m.managerId}`} ava={initials(m.name)} name={m.name} fact={m.revenueFact} plan={m.revenuePlan} fmtMoney />
          ))}
        </div>

        <div style={{ paddingLeft: 26 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <ColTag text="Брифы" tone="a" />
            {briefsMop > 0 ? <span style={{ fontSize: 11, color: 'var(--bb-faint)', marginLeft: 'auto', fontWeight: 500 }}>план {briefsMop} на каждого</span> : null}
          </div>
          {[...data.managers].sort((a, b) => b.briefsFact - a.briefsFact).map((m) => (
            <Row key={`br-${m.managerId}`} ava={initials(m.name)} name={m.name} fact={m.briefsFact} plan={m.briefsPlan} fmtMoney={false} />
          ))}
          <Row ava="ОП" name="Итого по МОП" fact={data.briefsTeamFact} plan={data.briefsTeamPlan} fmtMoney={false} team="a" />
        </div>
      </div>
    </div>
  );
}
