import type { PlanFact } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)}`;
}

function val(v: number, money_: boolean): string {
  return money_ ? money(v) : `${v}`;
}

export function PlanFactView({ data }: { data: PlanFact }) {
  return (
    <div className="bb-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
      {data.rows.map((r) => {
        const pct = r.pct ?? 0;
        const warn = pct < 60;
        return (
          <div key={r.key}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 13.5, fontWeight: 600 }}>{r.label}</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: warn ? '#d4202e' : '#15a85c' }}>
                {r.pct != null ? `${r.pct}%` : '—'}
              </span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--bb-muted)', margin: '4px 0 7px' }} className="tabular">
              {val(r.fact, r.money)} / {r.plan > 0 ? val(r.plan, r.money) : '—'}{' '}
              <span style={{ color: 'var(--bb-faint)' }}>· {r.basis}</span>
            </div>
            <div className="bb-pf-bar">
              <i
                style={{
                  width: `${Math.min(100, pct)}%`,
                  background: warn ? 'linear-gradient(90deg,#f2a93b,#e07b1a)' : undefined,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
