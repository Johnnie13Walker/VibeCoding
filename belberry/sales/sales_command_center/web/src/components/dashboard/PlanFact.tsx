import type { PlanFact, PlanFactManager } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)}`;
}

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase() || '—';
}

const pct = (fact: number, plan: number): number | null =>
  plan > 0 ? Math.round((fact / plan) * 100) : null;

function pctColor(p: number | null): string {
  if (p == null) return 'var(--bb-faint)';
  if (p >= 100) return 'var(--bb-green)';
  if (p >= 60) return '#b5651d';
  return 'var(--bb-red)';
}

/** Одна строка план/факт: имя + бар + факт/план + %. */
function Row({
  ava, name, role, fact, plan, fmtMoney, team,
}: {
  ava: string; name: string; role?: string; fact: number; plan: number; fmtMoney: boolean; team?: boolean;
}) {
  const p = pct(fact, plan);
  const fmt = (v: number) => (fmtMoney ? money(v) : `${v}`);
  const fillColor = p == null ? undefined
    : p >= 100 ? 'linear-gradient(90deg,#4bbf7b,#2c7a4a)'
    : p >= 60 ? 'linear-gradient(90deg,#f0a35a,#e88a3b)'
    : 'linear-gradient(90deg,#ef8d5e,#d4202e)';
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '210px 1fr 132px 56px', alignItems: 'center', gap: 14,
      padding: team ? '11px 10px' : '10px 0',
      margin: team ? '0 -10px' : undefined,
      background: team ? 'var(--bb-violet-soft)' : undefined,
      borderRadius: team ? 10 : undefined,
      borderBottom: team ? undefined : '1px solid var(--bb-line)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div className="bb-mrow-ava" style={{ width: 30, height: 30, flex: '0 0 30px', fontSize: 11, background: team ? 'linear-gradient(135deg,var(--bb-indigo),var(--bb-violet))' : undefined }}>{ava}</div>
        <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.15 }}>
          {name}{role ? <><br /><small style={{ fontWeight: 500, color: 'var(--bb-faint)', fontSize: 11.5 }}>{role}</small></> : null}
        </div>
      </div>
      <div className="bb-pf-bar" style={{ marginTop: 0 }}>
        <i style={{ width: `${Math.min(100, p ?? 0)}%`, background: fillColor }} />
      </div>
      <div className="tabular" style={{ textAlign: 'right', fontSize: 13, fontWeight: 700 }}>
        {fmt(fact)} <span style={{ color: 'var(--bb-faint)', fontWeight: 600 }}>/ {plan > 0 ? fmt(plan) : '—'}</span>
      </div>
      <div className="tabular" style={{ textAlign: 'right', fontSize: 13, fontWeight: 800, color: pctColor(p) }}>
        {p != null ? `${p}%` : '—'}
      </div>
    </div>
  );
}

function GroupHead({ title, hint }: { title: string; hint?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, margin: '22px 0 12px' }}>
      <h4 style={{ fontSize: 13.5, fontWeight: 700 }}>{title}</h4>
      {hint ? <span style={{ fontSize: 12, color: 'var(--bb-faint)' }}>{hint}</span> : null}
    </div>
  );
}

export function PlanFactView({ data }: { data: PlanFact }) {
  const briefsMop = data.managers[0]?.briefsPlan ?? 0;
  return (
    <div>
      {/* Оплаты: команда + индивидуальные */}
      <GroupHead title="Оплаты, ₽" hint="командный план + индивидуальные" />
      <Row ava="ОП" name="Команда — отдел продаж" fact={data.revenueTeamFact} plan={data.revenueTeamPlan} fmtMoney team />
      {data.managers.map((m: PlanFactManager) => (
        <Row key={`rev-${m.managerId}`} ava={initials(m.name)} name={m.name} role="МОП" fact={m.revenueFact} plan={m.revenuePlan} fmtMoney />
      ))}

      {/* Брифы по МОП */}
      <GroupHead title="Брифы" hint={briefsMop > 0 ? `план ${briefsMop} на каждого` : undefined} />
      {[...data.managers]
        .sort((a, b) => b.briefsFact - a.briefsFact)
        .map((m) => (
          <Row key={`br-${m.managerId}`} ava={initials(m.name)} name={m.name} role="МОП" fact={m.briefsFact} plan={m.briefsPlan} fmtMoney={false} />
        ))}
      <Row ava="ОП" name="Итого по МОП" fact={data.briefsTeamFact} plan={data.briefsTeamPlan} fmtMoney={false} team />
    </div>
  );
}
