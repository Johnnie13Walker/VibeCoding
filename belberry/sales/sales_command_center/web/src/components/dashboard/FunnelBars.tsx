'use client';

import { useEffect, useState } from 'react';
import type { FunnelStage } from '@/lib/dashboard';

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
      {data.map((s) => (
        <div className="bb-fbar" key={s.stage}>
          <span className="bb-fbar-name">{s.label}</span>
          <div className="bb-fbar-track">
            <div className="bb-fbar-fill" style={{ width: grown ? `${Math.max(10, (s.count / max) * 100)}%` : '0%' }}>
              {s.count}
            </div>
          </div>
          <span className="bb-fbar-amt tabular">{fmtMoney(s.amount)}</span>
        </div>
      ))}
    </div>
  );
}
