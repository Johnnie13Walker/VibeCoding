'use client';

import { useMemo, useState } from 'react';
import { Search, FolderOpen } from 'lucide-react';
import type { PortfolioData } from '@/lib/portfolio';
import { agencyBrand, filterProjects, nicheIcon, rubShort, type PortfolioProject } from '@/lib/portfolio-shared';

const NICHE_PREVIEW = 8; // сколько ниш показывать до «показать все»
const PAGE = 60;

type SortKey = 'client' | 'niche' | 'services' | 'period' | 'revenue';
// По умолчанию: текст — А-Я (asc), числа/годы — от большего (desc).
const DEFAULT_DIR: Record<SortKey, 'asc' | 'desc'> = { client: 'asc', niche: 'asc', services: 'asc', period: 'desc', revenue: 'desc' };
function yearOf(period: string): number {
  const ys = (period.match(/\d{4}/g) || []).map(Number);
  return ys.length ? Math.max(...ys) : 0;
}
function sortVal(p: PortfolioProject, key: SortKey): string | number {
  switch (key) {
    case 'client': return (p.brand || p.project).toLowerCase();
    case 'niche': return p.category.toLowerCase();
    case 'services': return p.services.join(' ').toLowerCase();
    case 'period': return yearOf(p.period);
    case 'revenue': return p.revenue ?? -1;
  }
}

function SortTh({ label, k, sort, onClick, align }: { label: string; k: SortKey; sort: { key: SortKey; dir: 'asc' | 'desc' } | null; onClick: (k: SortKey) => void; align?: 'right' }) {
  const active = sort?.key === k;
  return (
    <th onClick={() => onClick(k)} style={{ cursor: 'pointer', userSelect: 'none', textAlign: align, color: active ? 'var(--bb-violet)' : undefined, whiteSpace: 'nowrap' }}>
      {label}{active ? (sort!.dir === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
    </th>
  );
}

function ProjectRow({ p }: { p: PortfolioProject }) {
  const siteUrl = p.domain ? `https://${p.domain}` : null;
  const brand = agencyBrand(p.brand);
  return (
    <tr>
      <td>
        <div className="pf-cl">
          <span className={`pf-dot ${brand ?? 'none'}`} title={brand === 'acoola' ? 'Acoola Team' : brand === 'belberry' ? 'Belberry' : ''} />
          {siteUrl ? (
            <a href={siteUrl} target="_blank" rel="noopener noreferrer">{p.project} ↗</a>
          ) : (
            <span style={{ fontWeight: 700 }}>{p.project}</span>
          )}
        </div>
      </td>
      <td>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-start' }}>
          <span className="pf-badge" style={{ background: '#eef0f4', color: '#5a6473' }}>{p.category}</span>
          {p.subcategory && p.subcategory.trim().toLowerCase() !== 'не определено' ? (
            <span style={{ fontSize: 11.5, color: 'var(--bb-faint)', whiteSpace: 'nowrap' }}>{p.subcategory}</span>
          ) : null}
        </div>
      </td>
      <td>
        <div className="pf-servs">
          {p.services.map((s) => (
            <span key={s} className="pf-badge" style={{ background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>{s}</span>
          ))}
        </div>
      </td>
      <td style={{ color: 'var(--bb-faint)', whiteSpace: 'nowrap' }}>{p.period || '—'}</td>
      <td style={{ textAlign: 'right', whiteSpace: 'nowrap', fontWeight: p.revenue ? 700 : 400, color: p.revenue ? 'var(--bb-ink)' : 'var(--bb-faint)', fontVariantNumeric: 'tabular-nums' }}>
        {p.revenue ? rubShort(p.revenue) : '—'}
      </td>
      <td style={{ textAlign: 'right' }}>
        {p.caseUrl ? (
          <a href={p.caseUrl} target="_blank" rel="noopener noreferrer" className="pf-casebtn">📄 кейс</a>
        ) : null}
      </td>
    </tr>
  );
}

export function PortfolioView({ data }: { data: PortfolioData }) {
  const [niche, setNiche] = useState<string | null>(null);
  const [service, setService] = useState<string | null>(null);
  const [onlyWithCase, setOnlyWithCase] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' } | null>(null);
  const [query, setQuery] = useState('');
  const [showAllNiches, setShowAllNiches] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const filtered = useMemo(() => {
    const list = filterProjects(data.projects, { niche, service, onlyWithCase, query });
    if (!sort) return list;
    const { key, dir } = sort;
    const sorted = [...list].sort((a, b) => {
      const va = sortVal(a, key);
      const vb = sortVal(b, key);
      const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'ru');
      return dir === 'desc' ? -c : c;
    });
    return sorted;
  }, [data.projects, niche, service, onlyWithCase, query, sort]);

  const clickSort = (key: SortKey) =>
    setSort((prev) => (prev && prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: DEFAULT_DIR[key] }));
  const nichesToShow = showAllNiches ? data.niches : data.niches.slice(0, NICHE_PREVIEW);

  return (
    <div className="bb-page bb-fade">
      <div className="bb-hero bb-aurora" style={{ background: 'linear-gradient(135deg, #1f6a4f, #2b2a5e)' }}>
        <div className="bb-hero-row">
          <div style={{ flex: 1 }}>
            <div className="bb-hero-eyebrow">Кейсы и охват · обновляется ежедневно</div>
            <h1 className="bb-hero-title">Портфолио</h1>
            <div className="bb-hero-sub">С какими нишами и услугами мы работали — для подбора кейсов под клиента</div>
          </div>
          <div style={{ display: 'flex', gap: 22 }}>
            <div style={{ textAlign: 'center' }}><div style={{ fontSize: 24, fontWeight: 800 }}>{data.totalProjects}</div><div style={{ fontSize: 11, color: '#c9c5f0', textTransform: 'uppercase', letterSpacing: '.03em' }}>проекта</div></div>
            <div style={{ textAlign: 'center' }}><div style={{ fontSize: 24, fontWeight: 800 }}>{data.niches.length}</div><div style={{ fontSize: 11, color: '#c9c5f0', textTransform: 'uppercase', letterSpacing: '.03em' }}>ниш</div></div>
            <div style={{ textAlign: 'center' }}><div style={{ fontSize: 24, fontWeight: 800 }}>{data.withCaseCount}</div><div style={{ fontSize: 11, color: '#c9c5f0', textTransform: 'uppercase', letterSpacing: '.03em' }}>кейсов на сайте</div></div>
            <div style={{ textAlign: 'center' }}><div style={{ fontSize: 24, fontWeight: 800 }}>{data.withRevenueCount}</div><div style={{ fontSize: 11, color: '#c9c5f0', textTransform: 'uppercase', letterSpacing: '.03em' }}>с выручкой</div></div>
          </div>
        </div>
      </div>

      {/* Ниши */}
      <div className="bb-card" style={{ marginBottom: 16 }}>
        <div className="bb-sect-head">
          <span className="bb-sect-ic">🗂</span>
          <h2>Ниши, с которыми работали</h2>
          <small>клик — отфильтровать</small>
        </div>
        <div className="pf-niches">
          <div className={`pf-niche${niche === null ? ' on' : ''}`} onClick={() => setNiche(null)}>
            <span className="pf-av">🗂️</span>
            <div><div className="pf-nn">Все ниши</div><div className="pf-nc">{data.totalProjects} проектов</div></div>
          </div>
          {nichesToShow.map((n) => (
            <div key={n.niche} className={`pf-niche${niche === n.niche ? ' on' : ''}`} onClick={() => setNiche(niche === n.niche ? null : n.niche)}>
              <span className="pf-av">{nicheIcon(n.niche)}</span>
              <div><div className="pf-nn">{n.niche}</div><div className="pf-nc">{n.count} проектов</div></div>
            </div>
          ))}
        </div>
        {data.niches.length > NICHE_PREVIEW ? (
          <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--bb-violet)', cursor: 'pointer' }} onClick={() => setShowAllNiches((v) => !v)}>
            {showAllNiches ? 'свернуть ▴' : `показать все ${data.niches.length} ниш ▾`}
          </div>
        ) : null}
      </div>

      {/* Проекты */}
      <div className="bb-card">
        <div className="bb-sect-head">
          <span className="bb-sect-ic" style={{ background: '#fdf2e7', color: '#b5651d' }}><FolderOpen size={17} /></span>
          <h2>Проекты{niche ? ` · ${niche}` : ''}</h2>
          <small>{filtered.length} из {data.totalProjects}</small>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
          <div className="pf-search"><Search size={15} /><input placeholder="Поиск по названию / бренду…" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
          <button className={`pf-toggle${onlyWithCase ? ' on' : ''}`} onClick={() => setOnlyWithCase((v) => !v)}>
            ★ только с кейсом на сайте
          </button>
        </div>

        <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 16 }}>
          <span className={`pf-chip${service === null ? ' on' : ''}`} onClick={() => setService(null)}>Все услуги</span>
          {data.services.map((s) => (
            <span key={s.niche} className={`pf-chip${service === s.niche ? ' on' : ''}`} onClick={() => setService(service === s.niche ? null : s.niche)}>
              {s.niche} <small>· {s.count}</small>
            </span>
          ))}
        </div>

        {filtered.length === 0 ? (
          <p style={{ color: 'var(--bb-muted)' }}>Ничего не найдено под фильтры.</p>
        ) : (
          <>
            <table className="pf-tbl">
              <thead>
                <tr>
                  <SortTh label="Клиент" k="client" sort={sort} onClick={clickSort} />
                  <SortTh label="Ниша" k="niche" sort={sort} onClick={clickSort} />
                  <SortTh label="Услуги" k="services" sort={sort} onClick={clickSort} />
                  <SortTh label="Годы работы" k="period" sort={sort} onClick={clickSort} />
                  <SortTh label="Выручка" k="revenue" sort={sort} onClick={clickSort} align="right" />
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, limit).map((p) => <ProjectRow key={p.project} p={p} />)}
              </tbody>
            </table>
            {filtered.length > limit ? (
              <div style={{ textAlign: 'center', marginTop: 16 }}>
                <button className="pf-toggle" onClick={() => setLimit((l) => l + PAGE)}>Показать ещё ({filtered.length - limit})</button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
