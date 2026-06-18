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
    let entered = 0, won = 0, lost = 0, spam = 0, wonAmount = 0;
    for (const m of picked) {
      entered += m.entered; won += m.won; lost += m.lost; spam += m.spam; wonAmount += m.wonAmount;
      for (let o = 1; o <= FUNNEL_MAX_ORDER; o++) reached[o] += m.reached?.[o] ?? 0;
    }
    return { entered, reached, won, lost, spam, wonAmount, avgCheck: won > 0 ? Math.round(wonAmount / won) : 0 };
  }, [sel, managers]);

  if (!managers.length) return <LegacyFunnel data={data} />;

  const entered = agg.entered;
  const steps = FUNNEL_STEPS_10.map((s, i) => ({
    ...s,
    count: agg.reached[s.order] ?? 0,
    prev: i === 0 ? null : (agg.reached[FUNNEL_STEPS_10[i - 1].order] ?? 0),
  }));
  const denom = Math.max(entered, 1);
  // Главная утечка — переход с максимальной абсолютной потерей сделок.
  let leakIdx = -1, leakDrop = 0;
  steps.forEach((s, i) => {
    if (s.prev != null) {
      const d = s.prev - s.count;
      if (d > leakDrop) { leakDrop = d; leakIdx = i; }
    }
  });
  const pct = (n: number) => (entered > 0 ? Math.round((n / entered) * 100) : null);

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
      {/* воронка по стадиям (полная цепочка, событийно по входу) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {steps.map((s, i) => {
          const p = pct(s.count);
          const drop = s.prev != null ? s.prev - s.count : null;
          const isLeak = i === leakIdx && leakDrop > 0;
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
              <div style={{ width: 150, flex: '0 0 150px', textAlign: 'right', display: 'flex', flexDirection: 'column', gap: 0, alignItems: 'flex-end' }}>
                <span className="tabular" style={{ fontSize: 15, fontWeight: 800 }}>{p != null ? `${p}%` : '—'}</span>
                {drop != null && drop > 0 ? (
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: isLeak ? 'var(--bb-red)' : 'var(--bb-muted)' }}>−{drop}</span>
                ) : i === 0 ? (
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--bb-faint)' }}>вход</span>
                ) : null}
                {isLeak ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: '#fdecec', color: 'var(--bb-red)', fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 8px', marginTop: 2 }}>
                    ▼ главная утечка
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {leakIdx >= 0 && leakDrop > 0 ? (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--bb-line)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13.5, color: 'var(--bb-muted)' }}>
          <span style={{ width: 9, height: 9, borderRadius: 999, background: 'var(--bb-red)', flex: '0 0 9px' }} />
          <span>
            Узкое место — <b style={{ color: 'var(--bb-ink)' }}>{FUNNEL_STEPS_10[leakIdx - 1]?.label} → {FUNNEL_STEPS_10[leakIdx]?.label}</b>: теряется {leakDrop}{' '}
            {agg.won === 0 && leakIdx === FUNNEL_STEPS_10.length - 1 ? '(до оплаты не дошла ни одна)' : 'сделок'}.
          </span>
        </div>
      ) : null}
      </>
      )}
    </div>
  );
}
