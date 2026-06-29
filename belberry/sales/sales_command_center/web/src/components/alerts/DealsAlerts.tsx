'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Flame, ExternalLink, VolumeX } from 'lucide-react';
import type { AlertsData } from '@/lib/alerts';
import { BURNING_TOP, SILENT_TOP, burnComparator, filterSection, sectionManagers, type BurnSort } from '@/lib/alerts-filter';
import { BurningSortPicker } from '@/components/alerts/BurningSortPicker';
import { SectionPicker, dealUrl, fmtDate, fmtDateFull, daysAgo, rub } from '@/components/alerts/shared';

// Превентив (#5) пока шумит — handover-флаг частит (RESPONSIBLE_ID звонков
// варьируется), на пилоте набегает ~46 «критичных». Прячем блок до доработки
// чувствительности флагов. Данные (deal_risk_flags) продолжают собираться cron'ом.
const SHOW_PROCESS_RISK = false;

/** Вкладка «Сделки» (/alerts/deals) — триггеры по сделкам: Горит + Тишина. */
export function DealsAlerts({ data }: { data: AlertsData }) {
  const lookup = useMemo(() => new Map(data.managers.map((m) => [m.managerId, m])), [data.managers]);

  const burningManagers = useMemo(() => sectionManagers(data.burning, lookup), [data.burning, lookup]);
  const silentManagers = useMemo(() => sectionManagers(data.silent, lookup), [data.silent, lookup]);

  const [selB, setSelB] = useState<Set<number>>(() => new Set(burningManagers.map((m) => m.managerId)));
  const [selS, setSelS] = useState<Set<number>>(() => new Set(silentManagers.map((m) => m.managerId)));
  const [burnSort, setBurnSort] = useState<BurnSort>('nomove');

  const burning = useMemo(
    () => filterSection(data.burning, selB, burningManagers.length, BURNING_TOP, burnComparator(burnSort, data.snapshotDate)),
    [data.burning, selB, burningManagers.length, burnSort, data.snapshotDate],
  );
  const silent = useMemo(() => filterSection(data.silent, selS, silentManagers.length, SILENT_TOP), [data.silent, selS, silentManagers.length]);

  return (
    <>
      {/* Горит */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic" style={{ background: '#fdeced', color: '#d4202e' }}><Flame size={17} /></span>
          <h2>Горит</h2>
          <small>застрявшие сделки · топ-{burning.length}</small>
          <div style={{ display: 'flex', gap: 8 }}>
            <BurningSortPicker value={burnSort} onChange={setBurnSort} />
            <SectionPicker managers={burningManagers} selected={selB} onChange={setSelB} />
          </div>
        </div>
        {burning.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Горящих сделок нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {burning.map((d) => (
              <li key={d.dealId} className="bb-alert-row">
                <span className={`bb-sev ${d.severity}`} aria-hidden />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <a href={dealUrl(d.dealId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title">
                    {d.title} <ExternalLink size={12} />
                  </a>
                  <p className="bb-alert-meta">
                    {d.stageLabel} · {d.manager}
                    <span className={`bb-reason ${d.severity}`}>{d.reason}</span>
                  </p>
                </div>
                <div className="bb-comm">
                  <div className="bb-comm-lbl">последний контакт</div>
                  {d.lastCommAt ? (
                    <>
                      <div className="bb-comm-val">{fmtDateFull(d.lastCommAt)}</div>
                      {daysAgo(d.lastCommAt, data.snapshotDate) != null ? (
                        <div className="bb-comm-ago">{daysAgo(d.lastCommAt, data.snapshotDate)} дн. назад</div>
                      ) : null}
                    </>
                  ) : (
                    <div className="bb-comm-none">контакта не было</div>
                  )}
                </div>
                <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                  <p className="tabular" style={{ fontWeight: 700, fontSize: 14 }}>{rub(d.amount)}</p>
                  <p style={{ fontSize: 12, fontWeight: 600, color: d.severity === 'critical' ? '#d4202e' : '#b5651d' }}>
                    {d.stuckDays} дн. без движения
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Тишина — нет коммуникации с клиентом >14 дней */}
      <div className="bb-card" style={{ marginBottom: SHOW_PROCESS_RISK ? 16 : 0 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic" style={{ background: '#eef0fd', color: '#5b50d6' }}><VolumeX size={17} /></span>
          <h2>Тишина</h2>
          <small>нет коммуникации &gt;14 дней · {silent.length}</small>
          <SectionPicker managers={silentManagers} selected={selS} onChange={setSelS} />
        </div>
        {silent.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Сделок без коммуникации больше 14 дней нет.</p>
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {silent.map((d) => (
              <li key={d.dealId} className="bb-alert-row">
                <span className={`bb-sev ${d.severity}`} aria-hidden />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <a href={dealUrl(d.dealId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title">
                    {d.title} <ExternalLink size={12} />
                  </a>
                  <p className="bb-alert-meta">
                    {d.stageLabel} · {d.manager}
                    <span className={`bb-reason ${d.severity}`}>{d.reason}</span>
                  </p>
                </div>
                <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                  <p className="tabular" style={{ fontWeight: 700, fontSize: 14 }}>{rub(d.amount)}</p>
                  <p style={{ fontSize: 12, fontWeight: 600, color: d.severity === 'critical' ? '#d4202e' : '#b5651d' }}>
                    {d.lastCommAt ? `последний контакт ${fmtDate(d.lastCommAt)}` : `${d.silenceDays} дн. без контакта`}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Риск процесса — живые сделки с красными флагами (превентив). Скрыто до доработки флагов. */}
      {SHOW_PROCESS_RISK && (
        <div className="bb-card">
          <div className="bb-sect-head">
            <span className="bb-sect-ic" style={{ background: '#fdeced', color: '#d4202e' }}>⚠️</span>
            <h2>Риск процесса</h2>
            <small>живые сделки с провалами процесса · {data.processRisk.length}</small>
          </div>
          {data.processRisk.length === 0 ? (
            <p style={{ color: 'var(--bb-muted)' }}>Живых сделок с процессными рисками нет.</p>
          ) : (
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
              {data.processRisk.map((r) => (
                <li key={r.dealId} className="bb-alert-row">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <a href={dealUrl(r.dealId)} target="_blank" rel="noopener noreferrer" className="bb-alert-title" style={{ fontWeight: 600 }}>
                      {r.title} <ExternalLink size={12} />
                    </a>
                    <p className="bb-alert-meta">{r.stageLabel} · {r.manager}</p>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                      {r.flags.map((f, i) => (
                        <span key={i} style={{ fontSize: 11, fontWeight: 600, background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)', borderRadius: 6, padding: '2px 7px' }}>{f}</span>
                      ))}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                    <span className={`bb-reason ${r.severity === 'critical' ? 'critical' : ''}`}>{r.severity === 'critical' ? 'критично' : 'риск'}</span>
                    <p style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 4 }}>
                      <Link href="/audit" style={{ color: 'var(--bb-violet)' }}>разобрать →</Link>
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
