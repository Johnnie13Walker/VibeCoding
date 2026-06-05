import type { MonthRow } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return v > 0 ? `${Math.round(v)}` : '—';
}

const cell: React.CSSProperties = { padding: '9px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 12.5, fontWeight: 600 };

export function MonthlyDynamics({ data }: { data: MonthRow[] }) {
  if (data.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет данных за период.</p>;
  }
  const last = data.length - 1;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr>
            <th style={{ ...head, textAlign: 'left' }}>Месяц</th>
            <th style={{ ...head, textAlign: 'right' }}>Первых встреч</th>
            <th style={{ ...head, textAlign: 'right' }}>Презентаций</th>
            <th style={{ ...head, textAlign: 'right' }}>КП</th>
            <th style={{ ...head, textAlign: 'right' }}>Сделки</th>
            <th style={{ ...head, textAlign: 'right' }}>Оплаты, шт</th>
            <th style={{ ...head, textAlign: 'right' }}>Оплаты, ₽</th>
          </tr>
        </thead>
        <tbody>
          {data.map((m, i) => (
            <tr key={m.ym} style={i === last ? { fontWeight: 700 } : undefined}>
              <td style={{ ...cell, textAlign: 'left', fontWeight: i === last ? 700 : 600, textTransform: 'capitalize' }}>{m.label}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{m.first || '—'}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{m.defense || '—'}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{m.kp || '—'}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{m.deals || '—'}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{m.wonCount || '—'}</td>
              <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{money(m.wonAmount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Оплаты (шт/₽) наполняются с момента сбора выигранных сделок — за прошлые месяцы появятся после бэкофилла.
      </p>
    </div>
  );
}
