import type { Forecast } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} млн ₽`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс ₽`;
  return `${Math.round(v)} ₽`;
}

const chipUp: React.CSSProperties = {
  background: '#e9f8ef', color: '#15a85c', fontWeight: 700, fontSize: 13,
  borderRadius: 999, padding: '4px 11px',
};
const chipDn: React.CSSProperties = { ...chipUp, background: '#fdeced', color: '#d4202e' };

export function ForecastView({ data }: { data: Forecast }) {
  const onTrack = data.pct != null && data.pct >= 100;
  return (
    <div>
      <div style={{ display: 'flex', gap: 26, alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 32, fontWeight: 800 }}>{money(data.forecastClose)}</div>
          <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>прогноз закрытия</div>
        </div>
        <div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--bb-faint)' }}>
            {data.planRevenue > 0 ? money(data.planRevenue) : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--bb-faint)' }}>план месяца</div>
        </div>
        {data.pct != null ? <span style={onTrack ? chipUp : chipDn}>{data.pct}% плана</span> : null}
      </div>

      {data.paceExpected > 0 ? (
        <div style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 600 }}>
            <span>Темп (pacing) на сегодня</span>
            <span className="tabular" style={{ color: 'var(--bb-muted)' }}>
              факт {money(data.paid)} / ожид. {money(data.paceExpected)}
            </span>
          </div>
          <div className="bb-pf-bar" style={{ marginTop: 6 }}>
            <i style={{ width: `${Math.min(100, data.pacePct ?? 0)}%` }} />
          </div>
        </div>
      ) : null}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr style={{ color: 'var(--bb-faint)', fontSize: 12.5 }}>
            <th style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Стадия</th>
            <th style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Сумма ₽</th>
            <th style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Вероятн.</th>
            <th style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Взвешенно</th>
          </tr>
        </thead>
        <tbody>
          {data.byStage.map((s) => (
            <tr key={s.label}>
              <td style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>{s.label}</td>
              <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>{money(s.amount)}</td>
              <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)', color: 'var(--bb-muted)' }}>{Math.round(s.prob * 100)}%</td>
              <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)', fontWeight: 700 }}>{money(s.weighted)}</td>
            </tr>
          ))}
          <tr>
            <td style={{ textAlign: 'left', padding: '8px 8px', color: 'var(--bb-faint)', fontWeight: 700 }}>Взвешенная воронка</td>
            <td />
            <td />
            <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 700 }}>{money(data.weighted)}</td>
          </tr>
        </tbody>
      </table>

      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Прогноз = уже оплачено + взвешенная открытая воронка. Вероятности по стадиям калибруются по историческому win rate.
      </p>
    </div>
  );
}

/** Прогноз по воронке БЕЗ крупного хедлайна (он вынесен в плитки «План/факт»):
 *  темп + взвешенная воронка по стадиям. */
export function ForecastStages({ data }: { data: Forecast }) {
  return (
    <div>
      {data.paceExpected > 0 ? (
        <div style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 600 }}>
            <span>Темп (pacing) на сегодня</span>
            <span className="tabular" style={{ color: 'var(--bb-muted)' }}>
              факт {money(data.paid)} / ожид. {money(data.paceExpected)}
            </span>
          </div>
          <div className="bb-pf-bar" style={{ marginTop: 6 }}>
            <i style={{ width: `${Math.min(100, data.pacePct ?? 0)}%` }} />
          </div>
        </div>
      ) : null}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr style={{ color: 'var(--bb-faint)', fontSize: 12.5 }}>
            <th style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Стадия</th>
            <th style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Сумма ₽</th>
            <th style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Вероятн.</th>
            <th style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>Взвешенно</th>
          </tr>
        </thead>
        <tbody>
          {data.byStage.map((s) => (
            <tr key={s.label}>
              <td style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>{s.label}</td>
              <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)' }}>{money(s.amount)}</td>
              <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)', color: 'var(--bb-muted)' }}>{Math.round(s.prob * 100)}%</td>
              <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid var(--bb-line)', fontWeight: 700 }}>{money(s.weighted)}</td>
            </tr>
          ))}
          <tr>
            <td style={{ textAlign: 'left', padding: '8px 8px', color: 'var(--bb-faint)', fontWeight: 700 }}>Взвешенная воронка</td>
            <td />
            <td />
            <td className="tabular" style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 700 }}>{money(data.weighted)}</td>
          </tr>
        </tbody>
      </table>

      <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
        Прогноз = уже оплачено + взвешенная открытая воронка. Вероятности по стадиям калибруются по историческому win rate.
      </p>
    </div>
  );
}
