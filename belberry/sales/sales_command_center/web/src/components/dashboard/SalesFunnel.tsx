'use client';

import { useEffect, useMemo, useState } from 'react';
import type { SalesFunnel as SalesFunnelData } from '@/lib/dashboard';

function money(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн ₽`;
  if (value >= 1_000) return `${Math.round(value / 1_000)} тыс ₽`;
  return `${Math.round(value)} ₽`;
}

const chipStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 500,
  color: 'var(--bb-muted)',
  background: 'var(--bb-soft, #f1f0fb)',
  borderRadius: 999,
  padding: '5px 12px',
};

/** Старый рендер (счётчик событий) — fallback для пустого состояния без сейлов. */
function LegacyFunnel({ data }: { data: SalesFunnelData }) {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const max = Math.max(...data.steps.map((s) => s.count)) || 1;
  return (
    <div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={chipStyle}>Холодные: <b style={{ color: 'var(--bb-ink)' }}>{data.dealsCold}</b></span>
        <span style={chipStyle}>Входящие: <b style={{ color: 'var(--bb-ink)' }}>{data.dealsIncoming}</b></span>
        <span style={chipStyle}>Средний чек: <b style={{ color: 'var(--bb-ink)' }}>{data.avgCheck > 0 ? money(data.avgCheck) : '—'}</b></span>
      </div>
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

function firstName(full: string): string {
  const p = full.trim().split(/\s+/);
  return p.length >= 2 ? `${p[0]} ${p[1][0]}.` : full;
}

export function SalesFunnel({ data }: { data: SalesFunnelData }) {
  const managers = data.managers ?? [];
  const allIds = useMemo(() => managers.map((m) => m.managerId), [managers]);
  // Пустой набор = «весь отдел» (все выбраны).
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const isAll = sel.size === 0 || sel.size === allIds.length;

  const agg = useMemo(() => {
    const ids = sel.size ? sel : new Set(allIds);
    const picked = managers.filter((m) => ids.has(m.managerId));
    const sum = (k: 'dealsInWork' | 'kpDeals' | 'defenseDeals' | 'won' | 'briefingDeals' | 'cold' | 'incoming' | 'wonAmount') =>
      picked.reduce((s, m) => s + (m[k] || 0), 0);
    const won = sum('won');
    const wonAmount = sum('wonAmount');
    return {
      base: sum('dealsInWork'),
      kp: sum('kpDeals'),
      defense: sum('defenseDeals'),
      won,
      briefings: sum('briefingDeals'),
      cold: sum('cold'),
      incoming: sum('incoming'),
      avgCheck: won > 0 ? Math.round(wonAmount / won) : 0,
    };
  }, [sel, allIds, managers]);

  if (!managers.length) return <LegacyFunnel data={data} />;

  const { base, kp, defense, won } = agg;
  const rows = [
    { key: 'deals', label: 'Сделки в работе', sub: '', count: base, prev: null as number | null },
    { key: 'kp', label: 'Отправлено КП', sub: '', count: kp, prev: base },
    { key: 'defense', label: 'Дошли до защиты', sub: 'презентация КП', count: defense, prev: kp },
    { key: 'won', label: 'Оплатили', sub: '', count: won, prev: defense },
  ];
  const denom = Math.max(base, kp, defense, won, 1);
  // Главная утечка — переход с максимальной абсолютной потерей сделок.
  let leakKey = '';
  let leakDrop = 0;
  for (const r of rows) {
    if (r.prev != null) {
      const d = r.prev - r.count;
      if (d > leakDrop) { leakDrop = d; leakKey = r.key; }
    }
  }
  const pct = (n: number) => (base > 0 ? Math.round((n / base) * 100) : null);

  const toggle = (id: number) => {
    setSel((prev) => {
      // из «весь отдел» (пусто) первый клик → изолируем одного сейла
      if (prev.size === 0) return new Set([id]);
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      // пусто или все выбраны → нормализуем к «весь отдел»
      if (next.size === 0 || next.size === allIds.length) return new Set();
      return next;
    });
  };

  return (
    <div>
      {/* мульти-селектор сейлов */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        <button
          type="button"
          onClick={() => setSel(new Set())}
          style={{
            ...chipStyle, cursor: 'pointer', border: 0,
            background: isAll ? 'var(--bb-violet)' : 'var(--bb-soft, #f1f0fb)',
            color: isAll ? '#fff' : 'var(--bb-muted)', fontWeight: 600,
          }}
        >
          Весь отдел
        </button>
        {managers.map((m) => {
          const on = !isAll && sel.has(m.managerId);
          return (
            <button
              key={m.managerId}
              type="button"
              onClick={() => toggle(m.managerId)}
              style={{
                ...chipStyle, cursor: 'pointer', border: 0,
                background: on ? 'var(--bb-violet)' : 'var(--bb-soft, #f1f0fb)',
                color: on ? '#fff' : 'var(--bb-muted)',
              }}
            >
              {firstName(m.name)}
            </button>
          );
        })}
      </div>

      {/* плашки-контекст */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 18 }}>
        <span style={chipStyle}>Холодные: <b style={{ color: 'var(--bb-ink)' }}>{agg.cold}</b></span>
        <span style={chipStyle}>Входящие: <b style={{ color: 'var(--bb-ink)' }}>{agg.incoming}</b></span>
        <span style={chipStyle}>Первых встреч: <b style={{ color: 'var(--bb-ink)' }}>{agg.briefings}</b></span>
        <span style={chipStyle}>Средний чек: <b style={{ color: 'var(--bb-ink)' }}>{agg.avgCheck > 0 ? money(agg.avgCheck) : '—'}</b></span>
      </div>

      {/* воронка-когорта */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
        {rows.map((r) => {
          const p = pct(r.count);
          const drop = r.prev != null ? r.prev - r.count : null;
          const isLeak = r.key === leakKey && leakDrop > 0;
          const w = grown ? Math.max(8, (r.count / denom) * 100) : 0;
          const zero = r.count === 0;
          return (
            <div key={r.key} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ width: 180, flex: '0 0 180px' }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--bb-ink)' }}>{r.label}</div>
                {r.sub ? <div style={{ fontSize: 11, color: 'var(--bb-faint)' }}>{r.sub}</div> : null}
              </div>
              <div style={{ flex: 1, height: 38, background: '#f3f0ec', borderRadius: 10, overflow: 'hidden' }}>
                <div
                  className="tabular"
                  style={{
                    height: '100%', borderRadius: 10, width: `${w}%`, minWidth: 46,
                    background: zero ? '#cfcad9' : 'linear-gradient(90deg, var(--bb-violet), var(--bb-indigo))',
                    display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 14,
                    color: '#fff', fontWeight: 800, fontSize: 16,
                    transition: 'width .9s cubic-bezier(.22,1,.36,1)',
                  }}
                >
                  {r.count}
                </div>
              </div>
              <div style={{ width: 152, flex: '0 0 152px', textAlign: 'right', display: 'flex', flexDirection: 'column', gap: 1, alignItems: 'flex-end' }}>
                <span className="tabular" style={{ fontSize: 16, fontWeight: 800 }}>{p != null ? `${p}%` : '—'}</span>
                {drop != null ? (
                  <span style={{ fontSize: 12, fontWeight: 600, color: isLeak ? 'var(--bb-red)' : 'var(--bb-muted)' }}>
                    −{drop}
                  </span>
                ) : (
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--bb-faint)' }}>вход</span>
                )}
                {isLeak ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: '#fdecec', color: 'var(--bb-red)', fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '3px 9px', marginTop: 2 }}>
                    ▼ главная утечка
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {leakKey && leakDrop > 0 ? (
        <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--bb-line)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13.5, color: 'var(--bb-muted)' }}>
          <span style={{ width: 9, height: 9, borderRadius: 999, background: 'var(--bb-red)', flex: '0 0 9px' }} />
          <span>
            Узкое место — <b style={{ color: 'var(--bb-ink)' }}>{leakLabel(leakKey)}</b>: теряется {leakDrop}{' '}
            {leakKey === 'won' && won === 0 ? '(до оплаты не дошла ни одна)' : 'сделок'}.
          </span>
        </div>
      ) : null}
    </div>
  );
}

function leakLabel(key: string): string {
  if (key === 'kp') return 'Сделки → КП';
  if (key === 'defense') return 'КП → защита';
  if (key === 'won') return 'защита → оплата';
  return key;
}
