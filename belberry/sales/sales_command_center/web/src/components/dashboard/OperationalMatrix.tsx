import type { OperationalMatrix, OperationalRow } from '@/lib/operational';

function fmtDate(iso: string): string {
  const [, m, d] = iso.split('-');
  return d && m ? `${d}.${m}` : iso;
}

/** Цвет ячейки по баллу «Опер» 0–10 (heatmap: простой → высокая загрузка). */
function tone(v: number): { bg: string; fg: string } {
  if (v >= 8) return { bg: '#43b06a', fg: '#ffffff' };
  if (v >= 6.5) return { bg: '#8fcf6b', fg: '#1f4d2e' };
  if (v >= 5) return { bg: '#f3c34a', fg: '#5c4708' };
  if (v >= 3.5) return { bg: '#f0913e', fg: '#ffffff' };
  return { bg: '#e74c4c', fg: '#ffffff' };
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

const NAME_W = 210;
const COL_W = 58;

function Cell({ v }: { v: number | null }) {
  if (v == null) {
    return (
      <div style={{ height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#cbd2dc', fontWeight: 600 }}>
        —
      </div>
    );
  }
  const t = tone(v);
  return (
    <div
      className="tabular"
      style={{ height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14, background: t.bg, color: t.fg }}
    >
      {v.toFixed(1)}
    </div>
  );
}

function Row({ r, ncols }: { r: OperationalRow; ncols: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `${NAME_W}px repeat(${ncols}, ${COL_W}px) ${COL_W + 6}px`, gap: 4, alignItems: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, paddingRight: 8 }}>
        <b style={{ fontWeight: 600, fontSize: 14 }}>{r.name}</b>
        <span style={{ fontSize: 11, color: 'var(--bb-faint)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{r.role || '—'}</span>
      </div>
      {r.scores.map((v, i) => (
        <Cell key={i} v={v} />
      ))}
      <div className="tabular" style={{ height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, background: '#0f172a', color: '#fff' }}>
        {r.avg != null ? r.avg.toFixed(1) : '—'}
      </div>
    </div>
  );
}

function SectionLabel({ text }: { text: string }) {
  return (
    <div style={{ padding: '14px 0 4px', color: 'var(--bb-faint)', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em' }}>
      {text}
    </div>
  );
}

export function OperationalMatrixView({ data }: { data: OperationalMatrix }) {
  if (data.days.length === 0 || data.rows.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет данных по операционной активности.</p>;
  }
  const ncols = data.days.length;
  const op = data.rows.filter((r) => !r.isTm);
  const tm = data.rows.filter((r) => r.isTm);

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 18 }} className="bb-mq-grid">
        <Mini label="Средний Опер отдела" value={data.avgScore != null ? `${data.avgScore.toFixed(1)} / 10` : '—'} sub={`за ${ncols} раб. ${ncols === 1 ? 'день' : 'дн.'}`} />
        <Mini label="Загрузка дня" value={data.loadPct != null ? `${data.loadPct}%` : '—'} sub="живых минут из 300 «в руках»" />
        <Mini label="Лучший сотрудник" value={data.best ? data.best.score.toFixed(1) : '—'} sub={data.best?.name} />
        <Mini label="Сотрудников" value={`${data.countOp + data.countTm}`} sub={`ОП ${data.countOp} · ТМ ${data.countTm}`} />
      </div>

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: NAME_W + (ncols + 1) * (COL_W + 4) }}>
          {/* шапка дат */}
          <div style={{ display: 'grid', gridTemplateColumns: `${NAME_W}px repeat(${ncols}, ${COL_W}px) ${COL_W + 6}px`, gap: 4, marginBottom: 6, color: 'var(--bb-faint)', fontSize: 12.5 }}>
            <div style={{ fontWeight: 600 }}>Сотрудник</div>
            {data.days.map((d) => (
              <div key={d} style={{ textAlign: 'center', fontWeight: 600 }}>{fmtDate(d)}</div>
            ))}
            <div style={{ textAlign: 'center', fontWeight: 700, color: 'var(--bb-muted)' }}>Сред.</div>
          </div>

          {op.length > 0 ? <SectionLabel text="Отдел продаж" /> : null}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {op.map((r) => (
              <Row key={r.managerId} r={r} ncols={ncols} />
            ))}
          </div>

          {tm.length > 0 ? <SectionLabel text="Телемаркетинг" /> : null}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {tm.map((r) => (
              <Row key={r.managerId} r={r} ncols={ncols} />
            ))}
          </div>

          {/* среднее по отделу */}
          <div style={{ display: 'grid', gridTemplateColumns: `${NAME_W}px repeat(${ncols}, ${COL_W}px) ${COL_W + 6}px`, gap: 4, alignItems: 'center', marginTop: 12 }}>
            <div style={{ fontWeight: 800, fontSize: 14 }}>Среднее по отделу</div>
            {data.deptAvgByDay.map((v, i) => (
              <div key={i} className="tabular" style={{ height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14, background: '#eef0f6', color: '#475569' }}>
                {v != null ? v.toFixed(1) : '—'}
              </div>
            ))}
            <div className="tabular" style={{ height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, background: '#0f172a', color: '#fff' }}>
              {data.avgScore != null ? data.avgScore.toFixed(1) : '—'}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginTop: 18, color: 'var(--bb-muted)', fontSize: 12.5, flexWrap: 'wrap' }}>
        <span>Балл за день:</span>
        {[
          ['#e74c4c', '<3.5 простой'],
          ['#f0913e', '3.5–5'],
          ['#f3c34a', '5–6.5'],
          ['#8fcf6b', '6.5–8'],
          ['#43b06a', '≥8 высокая'],
          ['#eef0f4', 'нет данных'],
        ].map(([c, t]) => (
          <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <i style={{ width: 13, height: 13, borderRadius: 4, background: c, display: 'inline-block' }} />
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}
