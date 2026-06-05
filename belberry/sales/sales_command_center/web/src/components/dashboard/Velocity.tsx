import type { Velocity } from '@/lib/dashboard';

function money(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} млн`;
  if (v >= 1_000) return `${Math.round(v / 1_000)} тыс`;
  return `${Math.round(v)}`;
}

const agingColor: Record<string, string> = {
  '0-7': 'linear-gradient(90deg,#6f5ff2,#3a2cb8)',
  '7-14': 'linear-gradient(90deg,#6f5ff2,#3a2cb8)',
  '14-30': 'linear-gradient(90deg,#f2a93b,#e07b1a)',
  '30+': 'linear-gradient(90deg,#e8636e,#d4202e)',
};
const agingTag: Record<string, { text: string; color: string }> = {
  '14-30': { text: 'риск', color: '#e07b1a' },
  '30+': { text: 'горит', color: '#d4202e' },
};

export function VelocityView({ data }: { data: Velocity }) {
  const maxDays = Math.max(1, ...data.stages.map((s) => s.avgDays));
  const maxAmount = Math.max(1, ...data.aging.map((a) => a.amount));
  return (
    <div className="bb-grid" style={{ gridTemplateColumns: 'repeat(2,1fr)', gap: 22 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>
          Среднее время на стадии{' '}
          <span style={{ color: 'var(--bb-faint)', fontWeight: 500 }}>· оценка цикла ≈ {data.estimatedCycleDays} дн.</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {data.stages.map((s) => (
            <div key={s.stage} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 56px', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 13, color: 'var(--bb-muted)', fontWeight: 600 }}>{s.label}</span>
              <div style={{ background: '#f0eff7', borderRadius: 8, height: 28, overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${Math.max(6, (s.avgDays / maxDays) * 100)}%`,
                    height: '100%',
                    borderRadius: 8,
                    background: s.avgDays === maxDays ? 'linear-gradient(90deg,#e8636e,#d4202e)' : 'linear-gradient(90deg,#6f5ff2,#3a2cb8)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    paddingRight: 10,
                    color: '#fff',
                    fontWeight: 700,
                    fontSize: 13,
                  }}
                >
                  {s.avgDays}д
                </div>
              </div>
              <span style={{ fontSize: 12, color: 'var(--bb-faint)', textAlign: 'right' }}>{s.count} шт</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Деньги по возрасту в воронке</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {data.aging.map((a) => {
            const tag = agingTag[a.key];
            return (
              <div key={a.key} style={{ display: 'grid', gridTemplateColumns: '120px 1fr 84px', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 13, color: 'var(--bb-muted)', fontWeight: 600 }}>{a.label}</span>
                <div style={{ background: '#f0eff7', borderRadius: 8, height: 28, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.max(6, (a.amount / maxAmount) * 100)}%`,
                      height: '100%',
                      borderRadius: 8,
                      background: agingColor[a.key],
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'flex-end',
                      paddingRight: 10,
                      color: '#fff',
                      fontWeight: 700,
                      fontSize: 13,
                    }}
                  >
                    {money(a.amount)}
                  </div>
                </div>
                <span style={{ fontSize: 12, fontWeight: 600, textAlign: 'right', color: tag?.color ?? 'var(--bb-faint)' }}>
                  {tag ? tag.text : `${a.count} шт`}
                </span>
              </div>
            );
          })}
        </div>
        {data.agingRiskAmount > 0 ? (
          <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 10 }}>
            {money(data.agingRiskAmount)} ₽ висит дольше 30 дней — кандидаты на разбор или закрытие.
          </p>
        ) : null}
      </div>
    </div>
  );
}
