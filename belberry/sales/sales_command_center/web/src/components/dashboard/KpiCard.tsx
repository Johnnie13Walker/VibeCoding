'use client';

import { useEffect, useRef, useState } from 'react';
import { TrendingUp, TrendingDown, type LucideIcon } from 'lucide-react';
import { Sparkline } from './Sparkline';
import type { KpiDelta } from '@/lib/dashboard';

function useCountUp(target: number, dur = 900): number {
  const [v, setV] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      setV(target * e);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, dur]);
  return v;
}

export function KpiCard({
  label,
  value,
  fmt,
  Icon,
  delta,
  trend,
}: {
  label: string;
  value: number;
  fmt?: (n: number) => string;
  Icon: LucideIcon;
  delta?: KpiDelta;
  trend?: number[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const shown = useCountUp(value);
  const text = fmt ? fmt(shown) : Math.round(shown).toLocaleString('ru-RU');
  const up = delta?.dir === 'up';
  const down = delta?.dir === 'down';

  return (
    <div ref={ref} className="bb-lift" style={card}>
      <div style={lbl}>
        <Icon size={14} strokeWidth={2} color="#5b50d6" />
        {label}
      </div>
      <div className="tabular" style={num}>
        {text}
      </div>
      <div style={foot}>
        {delta && delta.pct !== null ? (
          <span style={{ ...chip, ...(down ? chipDown : chipUp) }}>
            {up ? <TrendingUp size={12} /> : down ? <TrendingDown size={12} /> : null}
            {delta.pct > 0 ? '+' : ''}
            {delta.pct}%
          </span>
        ) : (
          <span style={{ fontSize: 12, color: '#9a9aa0' }}>к прошлому мес.</span>
        )}
        {trend && trend.length > 1 ? (
          <span style={{ marginLeft: 'auto' }}>
            <Sparkline data={trend} color={down ? '#d4202e' : '#5b50d6'} />
          </span>
        ) : null}
      </div>
    </div>
  );
}

const card: React.CSSProperties = {
  background: '#fff',
  border: '1px solid var(--bb-line)',
  borderRadius: 18,
  padding: 18,
  boxShadow: 'var(--bb-shadow)',
};
const lbl: React.CSSProperties = { fontSize: 12, color: 'var(--bb-muted)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 };
const num: React.CSSProperties = { fontSize: 30, fontWeight: 800, letterSpacing: '-0.03em', marginTop: 8 };
const foot: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, minHeight: 22 };
const chip: React.CSSProperties = { fontSize: 12, fontWeight: 700, borderRadius: 999, padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: 3 };
const chipUp: React.CSSProperties = { background: '#e7f4ec', color: '#2c7a4a' };
const chipDown: React.CSSProperties = { background: '#fdeaec', color: '#d4202e' };
