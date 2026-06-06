import type { MeetingQuality } from '@/lib/dashboard';

function fmtDate(iso: string): string {
  const [, m, d] = iso.split('-');
  return d && m ? `${d}.${m}` : iso;
}

function Mini({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ background: 'var(--bb-soft, #f3f2fb)', borderRadius: 12, padding: '14px 16px' }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--bb-muted)' }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4 }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>{sub}</div> : null}
    </div>
  );
}

const cell: React.CSSProperties = { padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' };

export function MeetingQualityView({ data }: { data: MeetingQuality }) {
  if (data.count === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет разобранных встреч.</p>;
  }
  return (
    <div>
      <div
        style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 18 }}
        className="bb-mq-grid"
      >
        <Mini label="Средний балл" value={data.avgScore != null ? `${data.avgScore} / 10` : '—'} />
        <Mini label="Со след. шагом" value={data.pctNextStep != null ? `${data.pctNextStep}%` : '—'} />
        <Mini
          label="Балл защит"
          value={data.defenseAvg != null ? `${data.defenseAvg}` : '—'}
          sub={data.briefingAvg != null ? `брифинги ${data.briefingAvg}` : undefined}
        />
        <Mini label="Разобрано встреч" value={`${data.count}`} />
      </div>

      {data.problematic.length > 0 ? (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
          <thead>
            <tr style={{ color: 'var(--bb-faint)', fontSize: 12.5 }}>
              <th style={{ ...cell, textAlign: 'left' }}>Дата</th>
              <th style={{ ...cell, textAlign: 'left' }}>Менеджер</th>
              <th style={{ ...cell, textAlign: 'right' }}>Балл</th>
              <th style={{ ...cell, textAlign: 'left' }}>Что не так (из разбора)</th>
            </tr>
          </thead>
          <tbody>
            {data.problematic.map((p, i) => (
              <tr key={`${p.date}-${i}`}>
                <td style={{ ...cell, textAlign: 'left' }}>{fmtDate(p.date)}</td>
                <td style={{ ...cell, textAlign: 'left' }}>{p.manager}</td>
                <td
                  className="tabular"
                  style={{ ...cell, textAlign: 'right', fontWeight: 700, color: (p.score ?? 10) <= 5 ? '#d4202e' : 'inherit' }}
                >
                  {p.score ?? '—'}
                </td>
                <td style={{ ...cell, textAlign: 'left', color: 'var(--bb-muted)' }}>{p.note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
