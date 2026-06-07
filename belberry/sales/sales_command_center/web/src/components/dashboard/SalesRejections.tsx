import type { SalesRejections } from '@/lib/sales-rejections';

function rub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase() || '—';
}

/** Бейдж «доли отказов»: высокая = плохо (красный), средняя — amber, низкая — зелёный. */
function rateBadge(pct: number | null): React.CSSProperties {
  const base: React.CSSProperties = {
    display: 'inline-block', fontSize: 12, fontWeight: 700, borderRadius: 999, padding: '3px 9px',
  };
  if (pct == null) return { ...base, background: 'var(--bb-violet-soft)', color: 'var(--bb-muted)' };
  if (pct >= 40) return { ...base, background: '#fdeced', color: 'var(--bb-red)' };
  if (pct >= 25) return { ...base, background: '#fdf2e7', color: '#b5651d' };
  return { ...base, background: '#e7f4ec', color: 'var(--bb-green)' };
}

/** Карточка 1 — итог с начала года: KPI + помесячно + причины. */
export function SalesRejectionsView({ data }: { data: SalesRejections }) {
  const maxMonth = Math.max(...data.months.map((m) => m.count), 1);
  const maxReason = Math.max(...data.reasons.map((r) => r.count), 1);

  return (
    <div>
      {/* KPI-плитки */}
      <div className="bb-grid bb-grid-4" style={{ marginBottom: 20 }}>
        <div style={{ background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)', borderRadius: 14, padding: '14px 16px' }}>
          <div className="tabular" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.02em', color: 'var(--bb-red)' }}>{data.totalRejections}</div>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 4 }}>Отказов всего</div>
          <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 4 }}>{data.yearLabel} · без СПАМа</div>
        </div>
        <div style={{ background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)', borderRadius: 14, padding: '14px 16px' }}>
          <div className="tabular" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.02em', color: 'var(--bb-red)' }}>{rub(data.lostAmount)}</div>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 4 }}>Потеряно</div>
          <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 4 }}>сумма проигранных сделок</div>
        </div>
        <div style={{ background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)', borderRadius: 14, padding: '14px 16px' }}>
          <div className="tabular" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.02em' }}>{data.lossRate != null ? `${data.lossRate}%` : '—'}</div>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 4 }}>Доля отказов</div>
          <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 4 }}>отказы / (отказы + оплаты)</div>
        </div>
        <div style={{ background: 'var(--bb-canvas)', border: '1px solid var(--bb-line)', borderRadius: 14, padding: '14px 16px' }}>
          <div className="tabular" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.02em' }}>{rub(data.avgLoss)}</div>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--bb-faint)', fontWeight: 600, marginTop: 4 }}>Средняя потеря</div>
          <div style={{ fontSize: 12, color: 'var(--bb-muted)', marginTop: 4 }}>на одну сделку</div>
        </div>
      </div>

      {/* Помесячно */}
      <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Отказы по месяцам</h4>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 150, padding: '6px 4px 0', borderBottom: '1px solid var(--bb-line)', marginBottom: 8 }}>
        {data.months.map((m) => (
          <div key={m.ym} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, height: '100%', justifyContent: 'flex-end' }}>
            <span className="tabular" style={{ fontSize: 13, fontWeight: 800 }}>{m.count}</span>
            <div style={{ width: '100%', maxWidth: 46, height: `${Math.max(3, (m.count / maxMonth) * 100)}%`, borderRadius: '8px 8px 0 0', background: 'linear-gradient(180deg,#e88a3b,#d4202e)' }} />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 12, padding: '0 4px' }}>
        {data.months.map((m) => (
          <span key={m.ym} style={{ flex: 1, textAlign: 'center', fontSize: 12, color: 'var(--bb-muted)', fontWeight: 500 }}>{m.label}</span>
        ))}
      </div>

      {/* Причины */}
      <h4 style={{ fontSize: 13, fontWeight: 700, margin: '22px 0 10px' }}>Причины отказов</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.reasons.map((r) => (
          <div key={`${r.reasonId}`} style={{ display: 'grid', gridTemplateColumns: '210px 1fr 96px', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 13, color: 'var(--bb-ink)', fontWeight: 500 }}>{r.label}</span>
            <div style={{ height: 22, background: '#f3f0ec', borderRadius: 7, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.max(4, (r.count / maxReason) * 100)}%`, borderRadius: 7, background: 'linear-gradient(90deg,#f0a35a,#d4202e)' }} />
            </div>
            <span className="tabular" style={{ textAlign: 'right', fontSize: 12.5, fontWeight: 700 }}>
              {r.count} <span style={{ color: 'var(--bb-faint)', fontWeight: 600 }}>· {r.pct}%</span>
            </span>
          </div>
        ))}
        {data.reasons.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--bb-faint)' }}>Нет данных по причинам за период.</div>
        ) : null}
      </div>

      {data.spamExcluded > 0 ? (
        <div style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 12, paddingTop: 10, borderTop: '1px dashed var(--bb-line)' }}>
          + {data.spamExcluded} СПАМ-{data.spamExcluded === 1 ? 'лид' : 'лидов'} отсеяно — нецелевые, в отказы и «долю» не входят.
        </div>
      ) : null}
    </div>
  );
}

/** Карточка 2 — отказы по менеджерам. */
export function SalesRejectionsManagers({ data }: { data: SalesRejections }) {
  const maxAmount = Math.max(...data.managers.map((m) => m.lostAmount), 1);

  if (data.managers.length === 0) {
    return <div style={{ fontSize: 13, color: 'var(--bb-faint)' }}>Отказов с начала года не зафиксировано.</div>;
  }

  return (
    <table className="bb-table tabular">
      <thead>
        <tr>
          <th>Менеджер</th>
          <th className="r">Отказов</th>
          <th className="r">Потеряно ₽</th>
          <th className="r">Доля отказов</th>
          <th>Топ-причина</th>
        </tr>
      </thead>
      <tbody>
        {data.managers.map((m) => (
          <tr key={m.managerId}>
            <td>
              <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                <div className="bb-mrow-ava" style={{ width: 34, height: 34, flex: '0 0 34px', fontSize: 12 }}>{initials(m.name)}</div>
                <div><b style={{ fontSize: 14, fontWeight: 600 }}>{m.name}</b></div>
              </div>
            </td>
            <td className="r">{m.rejections}</td>
            <td className="r">
              {rub(m.lostAmount)}
              <div style={{ height: 7, borderRadius: 6, background: '#f0ece7', overflow: 'hidden', maxWidth: 160, marginTop: 5, marginLeft: 'auto' }}>
                <i style={{ display: 'block', height: '100%', width: `${(m.lostAmount / maxAmount) * 100}%`, borderRadius: 6, background: 'linear-gradient(90deg,#e88a3b,#d4202e)' }} />
              </div>
            </td>
            <td className="r">
              <span style={rateBadge(m.lossRate)}>{m.lossRate != null ? `${m.lossRate}%` : '—'}</span>
            </td>
            <td><span style={{ fontSize: 11.5, color: 'var(--bb-muted)' }}>{m.topReason ?? '—'}</span></td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td style={{ fontWeight: 800, borderTop: '2px solid var(--bb-line)' }}>Итого по действующим</td>
          <td className="r" style={{ fontWeight: 800, borderTop: '2px solid var(--bb-line)' }}>{data.managersRejections}</td>
          <td className="r" style={{ fontWeight: 800, borderTop: '2px solid var(--bb-line)' }}>{rub(data.managersLostAmount)}</td>
          <td className="r" style={{ fontWeight: 800, borderTop: '2px solid var(--bb-line)' }}>{data.managersLossRate != null ? `${data.managersLossRate}%` : '—'}</td>
          <td style={{ borderTop: '2px solid var(--bb-line)' }} />
        </tr>
      </tfoot>
    </table>
  );
}
