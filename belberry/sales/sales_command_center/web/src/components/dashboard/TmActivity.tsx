import type { TmActivity } from '@/lib/dashboard';

const cell: React.CSSProperties = { padding: '9px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 12.5, fontWeight: 600 };

function Mini({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ background: 'var(--bb-soft, #f3f2fb)', borderRadius: 12, padding: '14px 16px' }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--bb-muted)' }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4 }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>{sub}</div> : null}
    </div>
  );
}

export function TmActivityView({ data }: { data: TmActivity }) {
  if (data.zvonari === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет активности телемаркетинга.</p>;
  }
  return (
    <div>
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 18 }}>
        <Mini
          label="Дозвоны 60с+"
          value={`${data.calls60}`}
          sub={`${data.calls60PerZvonar} на звонаря · ${data.calls60PerDay} в день`}
        />
        <Mini label="Дозвоны 120с+" value={`${data.calls120}`} />
        <Mini
          label="Наборов всего"
          value={`${data.dials}`}
          sub={`${data.dialsPerZvonar} на звонаря · ${data.dialsPerDay} в день`}
        />
        <Mini label="Часы разговоров" value={`${data.talkHours} ч`} sub={`звонарей: ${data.zvonari}`} />
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
          <thead>
            <tr>
              <th style={{ ...head, textAlign: 'left' }}>Звонарь</th>
              <th style={{ ...head, textAlign: 'right' }}>Наборов</th>
              <th style={{ ...head, textAlign: 'right' }}>Дозвоны 60с+</th>
              <th style={{ ...head, textAlign: 'right' }}>Встреч назначено</th>
              <th style={{ ...head, textAlign: 'right' }}>Конверсия во встречу</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.managerId}>
                <td style={{ ...cell, textAlign: 'left', fontWeight: 600 }}>{r.name}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.dials}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.calls60}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.meetingsSet}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>
                  {r.convToMeeting != null ? `${r.convToMeeting}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Дозвон = разговор ≥60 секунд. Встреча засчитывается создателю (телемаркетологу).
      </p>
    </div>
  );
}
