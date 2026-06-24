'use client';

import { useEffect, useMemo, useState } from 'react';
import type { SalesFunnel as SalesFunnelData } from '@/lib/dashboard';
import { FUNNEL_MAX_ORDER, FUNNEL_STEPS_10 } from '@/lib/funnel-stages';
import { ManagerPicker } from './ManagerPicker';

function money(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн ₽`;
  if (value >= 1_000) return `${Math.round(value / 1_000)} тыс ₽`;
  return `${Math.round(value)} ₽`;
}

const chipStyle: React.CSSProperties = {
  fontSize: 13, fontWeight: 500, color: 'var(--bb-muted)',
  background: 'var(--bb-soft, #f1f0fb)', borderRadius: 999, padding: '5px 12px',
};

/** Старый рендер (счётчик событий) — fallback для пустого состояния. */
function LegacyFunnel({ data }: { data: SalesFunnelData }) {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const max = Math.max(...data.steps.map((s) => s.count)) || 1;
  return (
    <div>
      <div className="bb-funnel">
        {data.steps.map((s) => (
          <div className="bb-fbar" key={s.key}>
            <span className="bb-fbar-name">{s.label}</span>
            <div className="bb-fbar-track">
              <div className="bb-fbar-fill" style={{ width: grown ? `${Math.max(10, (s.count / max) * 100)}%` : '0%' }}>{s.count}</div>
            </div>
            <span className="bb-fbar-amt tabular">{s.convFromPrev != null ? `${s.convFromPrev}%` : ''}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SalesFunnel({ data }: { data: SalesFunnelData }) {
  const managers = useMemo(() => data.managers ?? [], [data.managers]);
  const [sel, setSel] = useState<Set<number>>(() => new Set(managers.map((m) => m.managerId)));
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const agg = useMemo(() => {
    const picked = managers.filter((m) => sel.has(m.managerId));
    const reached = new Array(FUNNEL_MAX_ORDER + 1).fill(0);
    const lostByOrder = new Array(FUNNEL_MAX_ORDER + 1).fill(0);
    let entered = 0, won = 0, lost = 0, spam = 0, wonAmount = 0;
    for (const m of picked) {
      entered += m.entered; won += m.won; lost += m.lost; spam += m.spam; wonAmount += m.wonAmount;
      for (let o = 1; o <= FUNNEL_MAX_ORDER; o++) {
        reached[o] += m.reached?.[o] ?? 0;
        lostByOrder[o] += m.lostByOrder?.[o] ?? 0;
      }
    }
    return { entered, reached, lostByOrder, won, lost, spam, wonAmount, avgCheck: won > 0 ? Math.round(wonAmount / won) : 0 };
  }, [sel, managers]);

  if (!managers.length) return <LegacyFunnel data={data} />;

  const entered = agg.entered;
  // На каждой стадии: count = дошли сюда; advanced = двинулись ДАЛЬШЕ (дошли до
  // следующей); lostHere = ушли в отвал, умерев на этой стадии; parked = ещё в работе.
  const steps = FUNNEL_STEPS_10.map((s, i) => {
    const count = agg.reached[s.order] ?? 0;
    const next = FUNNEL_STEPS_10[i + 1];
    const isLast = !next;
    const advanced = isLast ? null : (agg.reached[next.order] ?? 0);
    const lostHere = agg.lostByOrder[s.order] ?? 0;
    const parked = isLast ? 0 : Math.max(0, count - (advanced ?? 0) - lostHere);
    return { ...s, count, advanced, lostHere, parked, isLast };
  });
  const denom = Math.max(entered, 1);
  // Главная утечка — стадия, с которой НЕ двинулось дальше больше всего сделок
  // (отвал + застрявшие), среди стадий с successor'ом и ненулевым count.
  let leakIdx = -1, leakStuck = 0;
  steps.forEach((s, i) => {
    if (!s.isLast && s.count > 0) {
      const stuck = s.count - (s.advanced ?? 0);
      if (stuck > leakStuck) { leakStuck = stuck; leakIdx = i; }
    }
  });
  const pct = (n: number) => (entered > 0 ? Math.round((n / entered) * 100) : null);

  // Ячейка числа потока (дальше/отвал/в работе): цвет по типу, 0 и «нет данных» — бледно.
  const DIM = '#d3cfe0';
  const numCell = (value: number, kind: 'go' | 'lost' | 'park', show: boolean) => {
    const color = !show || value === 0 ? DIM
      : kind === 'lost' ? 'var(--bb-red)'
      : kind === 'go' ? 'var(--bb-ink)'
      : 'var(--bb-faint)';
    return (
      <div style={{ width: 62, flex: '0 0 62px', textAlign: 'right' }}>
        <span className="tabular" style={{ fontSize: 14, fontWeight: 800, color }}>{show ? value : '—'}</span>
      </div>
    );
  };
  const headCell = (text: string, width: number) => (
    <div style={{ width, flex: `0 0 ${width}px`, textAlign: 'right' }}>{text}</div>
  );

  return (
    <div>
      {/* мульти-селектор сейлов — общий ManagerPicker (как в «Отказах») */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <ManagerPicker managers={managers} selected={sel} onChange={setSel} />
      </div>

      {/* плашки-контекст */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 18 }}>
        <span style={chipStyle}>Вошло в воронку: <b style={{ color: 'var(--bb-ink)' }}>{entered}</b></span>
        {agg.spam > 0 ? <span style={chipStyle}>Спам исключён: <b style={{ color: 'var(--bb-ink)' }}>{agg.spam}</b></span> : null}
        <span style={chipStyle}>Отвал/отложено: <b style={{ color: 'var(--bb-ink)' }}>{agg.lost}</b></span>
        <span style={chipStyle}>Средний чек: <b style={{ color: 'var(--bb-ink)' }}>{agg.avgCheck > 0 ? money(agg.avgCheck) : '—'}</b></span>
      </div>

      {sel.size === 0 ? (
        <div style={{ padding: '28px 0', textAlign: 'center', color: 'var(--bb-faint)', fontSize: 14 }}>
          Никто не выбран — отметьте сейлов или нажмите «Все менеджеры».
        </div>
      ) : (
      <>
      {/* шапка колонок потока: % · дальше · отвал · в работе */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, marginBottom: 7, fontSize: 10.5, fontWeight: 700, letterSpacing: '.03em', textTransform: 'uppercase', color: 'var(--bb-faint)' }}>
        <div style={{ width: 190, flex: '0 0 190px' }} />
        <div style={{ flex: 1 }} />
        {headCell('%', 58)}
        {headCell('дальше', 62)}
        {headCell('отвал', 62)}
        {headCell('в работе', 62)}
      </div>
      {/* воронка по стадиям (полная цепочка, событийно по входу) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {steps.map((s, i) => {
          const p = pct(s.count);
          const isLeak = i === leakIdx && leakStuck > 0;
          const w = grown ? Math.max(s.count > 0 ? 6 : 0, (s.count / denom) * 100) : 0;
          const zero = s.count === 0;
          return (
            <div key={s.stage} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ width: 190, flex: '0 0 190px' }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--bb-ink)' }}>{s.label}</div>
                {s.sub ? <div style={{ fontSize: 11, color: 'var(--bb-faint)' }}>{s.sub}</div> : null}
              </div>
              <div style={{ flex: 1, height: 34, background: '#f3f0ec', borderRadius: 9, overflow: 'hidden' }}>
                <div
                  className="tabular"
                  style={{
                    height: '100%', borderRadius: 9, width: `${w}%`, minWidth: 42,
                    background: s.order === 9 && s.count > 0 ? 'linear-gradient(90deg,#2c7a4a,#1f5e38)'
                      : zero ? '#cfcad9' : 'linear-gradient(90deg, var(--bb-violet), var(--bb-indigo))',
                    display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 12,
                    color: '#fff', fontWeight: 800, fontSize: 15,
                    transition: 'width .9s cubic-bezier(.22,1,.36,1)',
                  }}
                >
                  {s.count}
                </div>
              </div>
              {/* % от входа + чип утечки */}
              <div style={{ width: 58, flex: '0 0 58px', textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
                <span className="tabular" style={{ fontSize: 16, fontWeight: 800, color: zero ? 'var(--bb-faint)' : 'var(--bb-ink)' }}>{p != null ? `${p}%` : '—'}</span>
                {isLeak ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, background: '#fdecec', color: 'var(--bb-red)', fontSize: 10, fontWeight: 700, borderRadius: 999, padding: '1px 7px', whiteSpace: 'nowrap' }}>
                    ▼ утечка
                  </span>
                ) : null}
              </div>
              {/* Поток С ЭТОЙ стадии: дальше / отвал / в работе */}
              {numCell(s.advanced ?? 0, 'go', !s.isLast && s.count > 0)}
              {numCell(s.lostHere, 'lost', !s.isLast && s.count > 0)}
              {numCell(s.parked, 'park', !s.isLast && s.count > 0)}
            </div>
          );
        })}
      </div>

      {leakIdx >= 0 && leakStuck > 0 ? (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--bb-line)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13.5, color: 'var(--bb-muted)' }}>
          <span style={{ width: 9, height: 9, borderRadius: 999, background: 'var(--bb-red)', flex: '0 0 9px' }} />
          <span>
            Главное узкое место — <b style={{ color: 'var(--bb-ink)' }}>{steps[leakIdx]?.label}</b>: с этой стадии дальше прошли{' '}
            <b style={{ color: 'var(--bb-ink)' }}>{steps[leakIdx]?.advanced}</b> из {steps[leakIdx]?.count}
            {(steps[leakIdx]?.lostHere ?? 0) > 0 ? <> — <b style={{ color: 'var(--bb-red)' }}>{steps[leakIdx]?.lostHere} в отвал</b></> : null}
            {(steps[leakIdx]?.parked ?? 0) > 0 ? `, ${steps[leakIdx]?.parked} ещё в работе` : ''}.
          </span>
        </div>
      ) : null}
      </>
      )}
    </div>
  );
}
