'use client';

import { useMemo, useState } from 'react';
import { Handshake, FileText, Zap, Ban } from 'lucide-react';
import type { LiveFeedItem } from '@/lib/live';

const PORTAL = 'https://belberrycrm.bitrix24.ru';
const SP_TYPE: Record<string, number> = { meeting: 1048, brief: 1056, kp: 1106 };

function entityUrl(e: LiveFeedItem): string | null {
  if (e.id == null) return null;
  if (e.kind === 'deal' || e.kind === 'reject') return `${PORTAL}/crm/deal/details/${e.id}/`;
  const t = SP_TYPE[e.kind];
  return t ? `${PORTAL}/crm/type/${t}/details/${e.id}/` : null;
}

const ICON: Record<string, React.ReactNode> = {
  meeting: <Handshake size={16} />, brief: <FileText size={16} />, kp: <FileText size={16} />, deal: <Zap size={16} />,
  reject: <Ban size={16} />,
};
const LABEL: Record<string, string> = { meeting: 'встреча', brief: 'бриф', kp: 'КП', deal: 'сделка', reject: 'отказ' };

function timeOnly(at: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }).format(new Date(at));
  } catch { return ''; }
}

const FILTERS: { key: string; label: string }[] = [
  { key: '', label: 'Все' },
  { key: 'meeting', label: 'Встречи' },
  { key: 'brief', label: 'Брифы' },
  { key: 'kp', label: 'КП' },
  { key: 'deal', label: 'Сделки' },
  { key: 'reject', label: 'Отказы' },
];

export function FeedView({ items, isArchive }: { items: LiveFeedItem[]; isArchive: boolean }) {
  const [f, setF] = useState('');
  const rows = useMemo(() => (f ? items.filter((e) => e.kind === f) : items), [items, f]);

  return (
    <div className="bb-card" style={{ marginTop: 16 }}>
      <div className="bb-sect-head"><span className="bb-sect-ic"><Zap size={17} /></span><h2>Лента</h2><small>события дня</small></div>
      {items.length === 0 ? (
        <p style={{ color: 'var(--bb-muted)' }}>{isArchive ? 'Событий за день не сохранено.' : 'Событий пока нет.'}</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 12 }}>
            {FILTERS.map((x) => (
              <button
                key={x.key}
                onClick={() => setF(x.key)}
                style={{
                  font: 'inherit', fontSize: 12.5, fontWeight: 600, borderRadius: 999, padding: '5px 12px', cursor: 'pointer',
                  border: '1px solid var(--bb-line)',
                  background: f === x.key ? 'var(--bb-violet)' : '#fff',
                  color: f === x.key ? '#fff' : 'var(--bb-muted)',
                  borderColor: f === x.key ? 'var(--bb-violet)' : 'var(--bb-line)',
                }}
              >
                {x.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {rows.map((e, i) => {
              const url = entityUrl(e);
              const inner = (
                <>
                  <span style={{ color: e.kind === 'reject' ? '#dc2626' : 'var(--bb-violet)', display: 'inline-flex', flex: '0 0 auto' }}>{ICON[e.kind]}</span>
                  <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <b style={{ fontWeight: 600 }}>{e.title}</b> <span style={{ color: 'var(--bb-faint)' }}>· {e.manager} · {LABEL[e.kind]}</span>
                  </span>
                  <span style={{ marginLeft: 'auto', color: 'var(--bb-faint)', fontSize: 12, whiteSpace: 'nowrap' }}>{timeOnly(e.at)}</span>
                </>
              );
              const base: React.CSSProperties = { display: 'flex', gap: 9, alignItems: 'center', fontSize: 13, padding: '8px 10px', border: '1px solid var(--bb-line)', borderRadius: 10, textDecoration: 'none', color: 'var(--bb-ink)' };
              return url ? (
                <a key={i} href={url} target="_blank" rel="noopener noreferrer" style={base} className="bb-feed-link">{inner}</a>
              ) : (
                <div key={i} style={base}>{inner}</div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
