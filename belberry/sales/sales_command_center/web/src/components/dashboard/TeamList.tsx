'use client';

import { useEffect, useState } from 'react';
import { ChevronRight, X, PhoneCall, Handshake, FileText, Zap, Clock } from 'lucide-react';
import { Sparkline } from './Sparkline';
import type { TeamMember } from '@/lib/dashboard';

function initials(name: string): string {
  const p = name.split(/\s+/).filter(Boolean);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase() || '—';
}

function Stat({ icon, value, label }: { icon: React.ReactNode; value: React.ReactNode; label: string }) {
  return (
    <div className="bb-dr-stat">
      <div className="bb-dr-stat-top">{icon}<b className="tabular">{value}</b></div>
      <span>{label}</span>
    </div>
  );
}

export function TeamList({ team, meetingsPlan }: { team: TeamMember[]; meetingsPlan: number }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const active = team.find((m) => m.managerId === openId) ?? null;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpenId(null);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (team.length === 0) {
    return <p style={{ color: 'var(--bb-muted)' }}>Нет данных активности за период.</p>;
  }

  return (
    <>
      <div className="bb-team">
        {team.map((m) => {
          const pct = Math.min(100, Math.round((m.meetingsHeld / meetingsPlan) * 100));
          const hit = m.meetingsHeld >= meetingsPlan;
          return (
            <button key={m.managerId} className="bb-mrow" onClick={() => setOpenId(m.managerId)}>
              <span className="bb-mrow-ava">{initials(m.name)}</span>
              <span className="bb-mrow-id">
                <b>{m.name}</b>
                {m.role ? <small>{m.role}</small> : null}
              </span>
              <span className="bb-mrow-bar"><i style={{ width: `${pct}%` }} /></span>
              <span className={`bb-mrow-badge ${hit ? 'hit' : ''}`}>{m.meetingsHeld} встреч</span>
              <ChevronRight size={16} className="bb-mrow-chev" />
            </button>
          );
        })}
      </div>

      {active ? (
        <>
          <div className="bb-drawer-scrim" onClick={() => setOpenId(null)} />
          <aside className="bb-drawer bb-fade" role="dialog" aria-label={`Менеджер ${active.name}`}>
            <button className="bb-drawer-x" onClick={() => setOpenId(null)} aria-label="Закрыть"><X size={18} /></button>
            <div className="bb-drawer-head">
              <span className="bb-mrow-ava lg">{initials(active.name)}</span>
              <div>
                <h3>{active.name}</h3>
                {active.role ? <div className="bb-muted small">{active.role}</div> : null}
              </div>
            </div>

            <div className="bb-dr-stats">
              <Stat icon={<Handshake size={15} />} value={active.meetingsHeld} label="встреч за месяц" />
              <Stat icon={<PhoneCall size={15} />} value={active.dials} label="наборов" />
              <Stat icon={<FileText size={15} />} value={active.kpSent} label="КП" />
              <Stat icon={<Zap size={15} />} value={active.dealsCreated} label="сделок создано" />
              <Stat icon={<Clock size={15} />} value={active.talkHours} label="часов в разговоре" />
              <Stat icon={<Handshake size={15} />} value={`${Math.min(100, Math.round((active.meetingsHeld / meetingsPlan) * 100))}%`} label={`к плану ${meetingsPlan}`} />
            </div>

            {active.trend.length > 1 ? (
              <div className="bb-dr-block">
                <h4>Тренд встреч за месяц</h4>
                <Sparkline data={active.trend} width={360} height={48} />
              </div>
            ) : null}

            <div className="bb-dr-block">
              <h4>Последние разборы встреч</h4>
              {active.meetings.length === 0 ? (
                <p className="bb-muted small">Разобранных встреч за период нет.</p>
              ) : (
                <ul className="bb-dr-meetings">
                  {active.meetings.map((mt, i) => (
                    <li key={i}>
                      <span className={`bb-score ${mt.score != null && mt.score >= 7 ? 'hi' : mt.score != null && mt.score >= 5 ? 'mid' : 'lo'}`}>
                        {mt.score != null ? `${mt.score}/10` : '—'}
                      </span>
                      <div>
                        <div className="bb-muted small">{mt.date}</div>
                        {mt.note ? <div className="small">{mt.note}</div> : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </>
      ) : null}
    </>
  );
}
