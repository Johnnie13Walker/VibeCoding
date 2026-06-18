'use client';

import { useEffect, useState } from 'react';
import type { FunnelStage } from '@/lib/dashboard';
import { NEW_STAGES_10 } from '@/lib/funnel-stages';

const newBadge: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em',
  color: 'var(--bb-violet)', background: 'var(--bb-violet-soft)', borderRadius: 5,
  padding: '1px 5px', marginLeft: 6,
};

function fmtMoney(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн`;
  if (value >= 1_000) return `${Math.round(value / 1_000)} тыс`;
  return `${Math.round(value)} ₽`;
}

export function FunnelBars({ data }: { data: FunnelStage[] }) {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  if (data.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет открытых сделок в воронке.</p>;
  }
  const max = Math.max(...data.map((d) => d.count)) || 1;

  return (
    <div className="bb-funnel">
      {data.map((s) => {
        const zero = s.count === 0;
        const isNew = zero && NEW_STAGES_10.has(s.stage);
        return (
          <div className="bb-fbar" key={s.stage}>
            <span className="bb-fbar-name" style={zero ? { color: 'var(--bb-faint)' } : undefined}>
              {s.label}{isNew ? <span style={newBadge}>нов.</span> : null}
            </span>
            <div className="bb-fbar-track">
              <div
                className="bb-fbar-fill"
                style={{
                  width: grown ? (zero ? '26px' : `${Math.max(10, (s.count / max) * 100)}%`) : '0%',
                  background: zero ? '#cfcad9' : undefined,
                }}
              >
                {s.count}
              </div>
            </div>
            <span className="bb-fbar-amt tabular" style={zero ? { color: 'var(--bb-faint)' } : undefined}>{fmtMoney(s.amount)}</span>
          </div>
        );
      })}
    </div>
  );
}
