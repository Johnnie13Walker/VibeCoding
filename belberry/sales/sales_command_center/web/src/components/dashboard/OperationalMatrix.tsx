'use client';

import { useState } from 'react';
import type { OperationalMatrix, OperationalRow } from '@/lib/operational';

interface TipState { top: number; left: number; row: OperationalRow; i: number }

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

/** Закрепляет первую колонку (имена/ярлыки) при горизонтальном скролле матрицы. */
const stickyCol: React.CSSProperties = {
  position: 'sticky',
  left: 0,
  zIndex: 2,
  background: '#fff',
  boxShadow: '6px 0 6px -6px rgba(15,23,42,.12)',
};

function Cell({ v, leave, hover }: { v: number | null; leave?: boolean; hover?: { onEnter: (rect: DOMRect) => void; onLeave: () => void } }) {
  const hoverProps = hover
    ? {
        onMouseEnter: (e: React.MouseEvent<HTMLDivElement>) => hover.onEnter(e.currentTarget.getBoundingClientRect()),
        onMouseLeave: hover.onLeave,
        style: { cursor: 'default' as const },
      }
    : {};
  if (leave) {
    return (
      <div {...hoverProps} style={{ ...(hoverProps as { style?: object }).style, height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#eef0fd', color: 'var(--bb-violet)', fontWeight: 700, fontSize: 11, letterSpacing: '.02em' }}>
        отп
      </div>
    );
  }
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
      {...hoverProps}
      className="tabular"
      style={{ ...(hoverProps as { style?: object }).style, height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14, background: t.bg, color: t.fg }}
    >
      {v.toFixed(1)}
    </div>
  );
}

function Row({ r, ncols, onCell, onLeaveCell }: { r: OperationalRow; ncols: number; onCell: (i: number, rect: DOMRect) => void; onLeaveCell: () => void }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `${NAME_W}px repeat(${ncols}, ${COL_W}px) ${COL_W + 6}px`, gap: 4, alignItems: 'center' }}>
      <div style={{ ...stickyCol, alignSelf: 'stretch', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 1, paddingRight: 8 }}>
        <b style={{ fontWeight: 600, fontSize: 14 }}>{r.name}</b>
        <span style={{ fontSize: 11, color: 'var(--bb-faint)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{r.role || '—'}</span>
      </div>
      {r.scores.map((v, i) => (
        <Cell
          key={i}
          v={v}
          leave={r.leave[i]}
          hover={v != null || r.leave[i] ? { onEnter: (rect) => onCell(i, rect), onLeave: onLeaveCell } : undefined}
        />
      ))}
      <div className="tabular" style={{ height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, background: '#0f172a', color: '#fff' }}>
        {r.avg != null ? r.avg.toFixed(1) : '—'}
      </div>
    </div>
  );
}

/** Всплывающая разбивка операционных показателей дня (fixed — не режется скроллом). */
function OperTip({ tip, days }: { tip: TipState; days: string[] }) {
  const { row, i } = tip;
  const a = row.actions[i];
  const lines: [string, string][] = [];
  if (row.leave[i]) {
    lines.push(['Статус', 'отпуск / отсутствие']);
  } else if (a) {
    lines.push(['Наборы', `${a.dials}${a.calls60 ? ` (дозвон 60с+: ${a.calls60})` : ''}`]);
    lines.push(['Чаты Wazzup', String(a.messenger)]);
    lines.push(['Письма', String(a.emails)]);
    lines.push(['Встречи', String(a.meetings)]);
    const mins = row.minutes[i];
    if (mins != null) lines.push(['Живые минуты', `${Math.round(mins)} → балл ${row.scores[i]?.toFixed(1)}`]);
  }
  return (
    <div
      style={{
        position: 'fixed', top: tip.top - 10, left: tip.left, transform: 'translate(-50%, -100%)', zIndex: 60,
        background: '#1d1d1f', color: '#fff', borderRadius: 10, padding: '9px 12px', fontSize: 12, lineHeight: 1.5,
        whiteSpace: 'nowrap', boxShadow: '0 10px 28px -8px rgba(0,0,0,.45)', pointerEvents: 'none', textAlign: 'left',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 5 }}>{row.name} · {days[i] ? fmtDate(days[i]) : ''}</div>
      {lines.map(([k, val]) => (
        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 14 }}>
          <span style={{ opacity: 0.7 }}>{k}</span>
          <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{val}</span>
        </div>
      ))}
    </div>
  );
}

function SectionLabel({ text }: { text: string }) {
  return (
    <div style={{ position: 'sticky', left: 0, zIndex: 2, width: 'fit-content', padding: '14px 0 4px', color: 'var(--bb-faint)', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em' }}>
      {text}
    </div>
  );
}

export function OperationalMatrixView({ data }: { data: OperationalMatrix }) {
  const [tip, setTip] = useState<TipState | null>(null);
  if (data.days.length === 0 || data.rows.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>За период нет данных по операционной активности.</p>;
  }
  const ncols = data.days.length;
  const op = data.rows.filter((r) => !r.isTm);
  const tm = data.rows.filter((r) => r.isTm);
  const rowHover = (r: OperationalRow) => ({
    onCell: (i: number, rect: DOMRect) => setTip({ top: rect.top, left: rect.left + rect.width / 2, row: r, i }),
    onLeaveCell: () => setTip(null),
  });

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
            <div style={{ ...stickyCol, zIndex: 3, fontWeight: 600 }}>Сотрудник</div>
            {data.days.map((d) => (
              <div key={d} style={{ textAlign: 'center', fontWeight: 600 }}>{fmtDate(d)}</div>
            ))}
            <div style={{ textAlign: 'center', fontWeight: 700, color: 'var(--bb-muted)' }}>Сред.</div>
          </div>

          {op.length > 0 ? <SectionLabel text="Отдел продаж" /> : null}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {op.map((r) => (
              <Row key={r.managerId} r={r} ncols={ncols} {...rowHover(r)} />
            ))}
          </div>

          {tm.length > 0 ? <SectionLabel text="Телемаркетинг" /> : null}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {tm.map((r) => (
              <Row key={r.managerId} r={r} ncols={ncols} {...rowHover(r)} />
            ))}
          </div>

          {/* среднее по отделу */}
          <div style={{ display: 'grid', gridTemplateColumns: `${NAME_W}px repeat(${ncols}, ${COL_W}px) ${COL_W + 6}px`, gap: 4, alignItems: 'center', marginTop: 12 }}>
            <div style={{ ...stickyCol, display: 'flex', alignItems: 'center', fontWeight: 800, fontSize: 14 }}>Среднее по отделу</div>
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
          ['#eef0fd', 'отпуск'],
        ].map(([c, t]) => (
          <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <i style={{ width: 13, height: 13, borderRadius: 4, background: c, display: 'inline-block' }} />
            {t}
          </span>
        ))}
      </div>

      {tip ? <OperTip tip={tip} days={data.days} /> : null}
    </div>
  );
}
