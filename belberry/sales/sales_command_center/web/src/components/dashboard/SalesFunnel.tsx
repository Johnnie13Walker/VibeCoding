'use client';

import { useEffect, useState } from 'react';
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

export function SalesFunnel({ data }: { data: SalesFunnelData }) {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const max = Math.max(...data.steps.map((s) => s.count)) || 1;

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={chipStyle}>
          Холодные: <b style={{ color: 'var(--bb-ink, #1a1a2e)' }}>{data.dealsCold}</b>
        </span>
        <span style={chipStyle}>
          Входящие: <b style={{ color: 'var(--bb-ink, #1a1a2e)' }}>{data.dealsIncoming}</b>
        </span>
        <span style={chipStyle}>
          Средний чек: <b style={{ color: 'var(--bb-ink, #1a1a2e)' }}>{data.avgCheck > 0 ? money(data.avgCheck) : '—'}</b>
        </span>
      </div>

      <div className="bb-funnel">
        {data.steps.map((s) => {
          const conv = s.convFromPrev != null ? `${s.convFromPrev}%` : '';
          const right =
            s.key === 'won'
              ? [conv, s.amount ? money(s.amount) : null].filter(Boolean).join(' · ')
              : conv;
          return (
            <div className="bb-fbar" key={s.key}>
              <span className="bb-fbar-name">{s.label}</span>
              <div className="bb-fbar-track">
                <div
                  className="bb-fbar-fill"
                  style={{ width: grown ? `${Math.max(10, (s.count / max) * 100)}%` : '0%' }}
                >
                  {s.count}
                </div>
              </div>
              <span className="bb-fbar-amt tabular">{right}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
