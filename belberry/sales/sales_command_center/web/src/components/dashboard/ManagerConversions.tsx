import type { ManagerConversion } from '@/lib/dashboard';

const cell: React.CSSProperties = { padding: '9px 10px', borderBottom: '1px solid var(--bb-line)' };
const head: React.CSSProperties = { ...cell, color: 'var(--bb-faint)', fontSize: 12.5, fontWeight: 600 };

function pct(v: number | null): string {
  return v == null ? '—' : `${v}%`;
}

function Row({ m, bold }: { m: ManagerConversion; bold?: boolean }) {
  return (
    <tr style={bold ? { color: 'var(--bb-faint)', fontWeight: 700 } : undefined}>
      <td style={{ ...cell, textAlign: 'left', fontWeight: bold ? 700 : 600 }}>{m.name}</td>
      <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{pct(m.dealToMeeting)}</td>
      <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{pct(m.meetingToDefense)}</td>
      <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{pct(m.defenseToWon)}</td>
      <td className="tabular" style={{ ...cell, textAlign: 'right' }}>{pct(m.dealToWon)}</td>
    </tr>
  );
}

export function ManagerConversions({
  data,
}: {
  data: { managers: ManagerConversion[]; total: ManagerConversion };
}) {
  if (data.managers.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет активности менеджеров.</p>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr>
            <th style={{ ...head, textAlign: 'left' }}>Менеджер</th>
            <th style={{ ...head, textAlign: 'right' }}>Сделка → встреча</th>
            <th style={{ ...head, textAlign: 'right' }}>Встреча → защита</th>
            <th style={{ ...head, textAlign: 'right' }}>Защита → оплата</th>
            <th style={{ ...head, textAlign: 'right' }}>Сделка → оплата</th>
          </tr>
        </thead>
        <tbody>
          {data.managers.map((m) => (
            <Row key={m.managerId} m={m} />
          ))}
          <Row m={data.total} bold />
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Конверсии &gt;100% — тайминг периода (встречи опережают сделки). Оплаты наполнятся после бэкофилла.
      </p>
    </div>
  );
}
