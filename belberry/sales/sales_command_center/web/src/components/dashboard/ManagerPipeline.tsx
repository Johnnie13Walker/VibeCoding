import type { ManagerPipeline } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)}`;
}

const cell: React.CSSProperties = { padding: '9px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 12.5, fontWeight: 600 };

function Delta({ v }: { v: number }) {
  if (v === 0) return <span style={{ color: 'var(--bb-faint)' }}>0</span>;
  const up = v > 0;
  return (
    <span style={{ color: up ? '#15a85c' : '#d4202e', fontWeight: 700 }}>
      {up ? '▲ +' : '▼ '}
      {v}
    </span>
  );
}

export function ManagerPipelineView({ data }: { data: ManagerPipeline }) {
  if (data.rows.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет открытых сделок по менеджерам.</p>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, whiteSpace: 'nowrap' }}>
        <thead>
          <tr>
            <th style={{ ...head, textAlign: 'left' }}>Менеджер</th>
            {data.stages.map((s) => (
              <th key={s.stage} style={{ ...head, textAlign: 'right' }}>{s.label}</th>
            ))}
            <th style={{ ...head, textAlign: 'right' }}>Σ сделок</th>
            <th style={{ ...head, textAlign: 'right' }}>Σ ₽</th>
            <th style={{ ...head, textAlign: 'right' }}>Δ за месяц</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.managerId}>
              <td style={{ ...cell, textAlign: 'left', fontWeight: 600 }}>{r.name}</td>
              {data.stages.map((s) => (
                <td key={s.stage} className="tabular" style={{ ...cell, textAlign: 'right' }}>
                  {r.counts[s.stage] ?? <span style={{ color: 'var(--bb-faint)' }}>—</span>}
                </td>
              ))}
              <td className="tabular" style={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{r.total}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{money(r.amount)}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}><Delta v={r.delta} /></td>
            </tr>
          ))}
          <tr style={{ color: 'var(--bb-faint)', fontWeight: 700 }}>
            <td style={{ ...cell, textAlign: 'left' }}>Итого</td>
            {data.stages.map((s) => (
              <td key={s.stage} className="tabular" style={{ ...cell, textAlign: 'right' }}>{data.stageTotal[s.stage] ?? 0}</td>
            ))}
            <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{data.grandTotal}</td>
            <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{money(data.grandAmount)}</td>
            <td />
          </tr>
          <tr style={{ color: 'var(--bb-faint)', fontSize: 12.5 }}>
            <td style={{ ...cell, textAlign: 'left' }}>Сумма ₽ по стадии</td>
            {data.stages.map((s) => (
              <td key={s.stage} className="tabular" style={{ ...cell, textAlign: 'right' }}>{money(data.stageAmount[s.stage] ?? 0)}</td>
            ))}
            <td colSpan={3} />
          </tr>
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Δ — изменение числа открытых сделок у менеджера с начала месяца. Видно, где у кого «застряли» деньги.
      </p>
    </div>
  );
}
