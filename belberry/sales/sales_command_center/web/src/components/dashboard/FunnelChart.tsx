'use client';

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { FunnelStage } from '@/lib/dashboard';

// Брендовый рамп фиолет → индиго (Belberry «Командный центр»).
const SHADES = ['#5b50d6', '#4f46b8', '#423d96', '#363276', '#2b2a5e'];

function fmtMoney(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн ₽`;
  if (value >= 1_000) return `${Math.round(value / 1_000)} тыс ₽`;
  return `${Math.round(value)} ₽`;
}

export function FunnelChart({ data }: { data: FunnelStage[] }) {
  if (data.length === 0) {
    return <p className="text-[0.95rem] text-[#6e6e73]">Нет открытых сделок в воронке.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 56)}>
      <BarChart layout="vertical" data={data} margin={{ top: 4, right: 88, bottom: 4, left: 8 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={150}
          tickLine={false}
          axisLine={false}
          tick={{ fill: '#1d1d1f', fontSize: 13 }}
        />
        <Tooltip
          cursor={{ fill: '#f5f5f7' }}
          formatter={(value, _name, item) => [
            `${fmtMoney(Number(value ?? 0))} · ${(item?.payload as FunnelStage)?.count ?? 0} сд.`,
            'Сумма',
          ]}
          contentStyle={{
            borderRadius: 12,
            border: '1px solid #e8e8ed',
            fontSize: 13,
            boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
          }}
        />
        <Bar dataKey="amount" radius={[8, 8, 8, 8]} barSize={26}>
          {data.map((stage, i) => (
            <Cell key={stage.stage} fill={SHADES[i % SHADES.length]} />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            formatter={(v) => `${v ?? 0} сд.`}
            fill="#6e6e73"
            fontSize={12}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
