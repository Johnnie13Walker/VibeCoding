import type { Messaging } from '@/lib/dashboard';

const cell: React.CSSProperties = { padding: '9px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 12.5, fontWeight: 600 };

export function MessagingView({ data }: { data: Messaging }) {
  if (data.rows.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет переписок и писем.</p>;
  }
  return (
    <div>
      <div style={{ display: 'flex', gap: 26, alignItems: 'baseline', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 28, fontWeight: 800 }}>{data.messengerTotal}</div>
          <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>диалогов в мессенджере</div>
        </div>
        <div>
          <div style={{ fontSize: 28, fontWeight: 800 }}>{data.emailTotal}</div>
          <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>писем отправлено</div>
        </div>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
          <thead>
            <tr>
              <th style={{ ...head, textAlign: 'left' }}>Менеджер</th>
              <th style={{ ...head, textAlign: 'right' }}>Мессенджер</th>
              <th style={{ ...head, textAlign: 'right' }}>Почта</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.managerId}>
                <td style={{ ...cell, textAlign: 'left', fontWeight: 600 }}>{r.name}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.messenger}</td>
                <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{r.emails}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
