import type { Day2Day } from '@/lib/dashboard';

const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

function fmt(iso: string): { day: string; wd: string; weekend: boolean } {
  const d = new Date(`${iso}T00:00:00Z`);
  const wd = d.getUTCDay();
  const [, m, dd] = iso.split('-');
  return { day: `${dd}.${m}`, wd: WD[wd], weekend: wd === 0 || wd === 6 };
}

const cell: React.CSSProperties = { padding: '8px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 12.5, fontWeight: 600 };

export function Day2DayView({ data }: { data: Day2Day }) {
  if (data.rows.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет дневной статистики за месяц.</p>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr>
            <th style={{ ...head, textAlign: 'left' }}>День</th>
            <th style={{ ...head, textAlign: 'right' }}>Сделки</th>
            <th style={{ ...head, textAlign: 'right' }}>Встречи</th>
            <th style={{ ...head, textAlign: 'right' }}>КП</th>
            <th style={{ ...head, textAlign: 'right' }}>Наборы</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => {
            const f = fmt(r.date);
            return (
              <tr key={r.date} style={f.weekend ? { color: 'var(--bb-faint)' } : undefined}>
                <td style={{ ...cell, textAlign: 'left', fontWeight: 600 }}>
                  {f.day} <span style={{ color: 'var(--bb-faint)', fontWeight: 400 }}>{f.wd}</span>
                </td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.deals || '·'}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.meetings || '·'}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.kp || '·'}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.dials || '·'}</td>
              </tr>
            );
          })}
          <tr style={{ fontWeight: 700 }}>
            <td style={{ ...cell, textAlign: 'left' }}>Итого</td>
            <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{data.total.deals}</td>
            <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{data.total.meetings}</td>
            <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{data.total.kp}</td>
            <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{data.total.dials}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
