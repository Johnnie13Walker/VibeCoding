'use client';

import { useEffect, useState } from 'react';

/** Радиальный «здоровье»-gauge 0-100 с анимацией дуги при монтировании. */
export function Gauge({ value, label = 'здоровье' }: { value: number; label?: string }) {
  const R = 50;
  const C = 2 * Math.PI * R;
  const [offset, setOffset] = useState(C);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const id = requestAnimationFrame(() => setOffset(C - (C * Math.min(100, Math.max(0, value))) / 100));
    const start = performance.now();
    const dur = 900;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(value * e));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(id);
      cancelAnimationFrame(raf);
    };
  }, [value, C]);

  return (
    <div style={{ position: 'relative', width: 118, height: 118, flex: '0 0 118px' }}>
      <svg width={118} height={118} viewBox="0 0 118 118" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={59} cy={59} r={R} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth={11} />
        <circle
          cx={59}
          cy={59}
          r={R}
          fill="none"
          stroke="url(#bbGauge)"
          strokeWidth={11}
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(.22,1,.36,1)' }}
        />
        <defs>
          <linearGradient id="bbGauge" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#8b80ff" />
            <stop offset="1" stopColor="#e88a3b" />
          </linearGradient>
        </defs>
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'grid',
          placeItems: 'center',
          textAlign: 'center',
        }}
      >
        <div>
          <b style={{ fontSize: 30, fontWeight: 800, color: '#fff', lineHeight: 1 }} className="tabular">
            {shown}
          </b>
          <small
            style={{
              display: 'block',
              color: '#c9c5f0',
              fontSize: 10.5,
              fontWeight: 600,
              marginTop: 2,
              textTransform: 'uppercase',
              letterSpacing: '.08em',
            }}
          >
            {label}
          </small>
        </div>
      </div>
    </div>
  );
}
