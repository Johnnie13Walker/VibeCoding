'use client';

import { useMemo, useState } from 'react';
import { ExternalLink, Search, FolderOpen } from 'lucide-react';
import type { PortfolioData } from '@/lib/portfolio';
import { filterProjects, nicheIcon, type PortfolioProject } from '@/lib/portfolio-shared';

const NICHE_PREVIEW = 8; // сколько ниш показывать до «показать все»
const PAGE = 60;

function CaseCard({ p }: { p: PortfolioProject }) {
  const siteUrl = p.domain ? `https://${p.domain}` : null;
  return (
    <div className="pf-case">
      <div>
        <div style={{ fontSize: 15.5, fontWeight: 700, lineHeight: 1.25 }}>{p.brand || p.project}</div>
        <div style={{ fontSize: 12, color: 'var(--bb-faint)', marginTop: 2 }}>
          {p.domain ?? p.project}
          {p.period ? ` · ${p.period}` : ''}
          {p.experienceMonths ? ` · ${p.experienceMonths} мес.` : ''}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <span className="pf-badge" style={{ background: '#e6f4ea', color: '#1a7f37' }}>{p.category}</span>
        {p.services.slice(0, 4).map((s) => (
          <span key={s} className="pf-badge" style={{ background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>{s}</span>
        ))}
        {p.caseUrl ? <span className="pf-badge" style={{ background: '#fff4e6', color: '#b5651d' }}>★ кейс на сайте</span> : null}
      </div>
      {p.caseDescription ? (
        <div style={{ fontSize: 13, color: 'var(--bb-muted)', lineHeight: 1.4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {p.caseDescription}
        </div>
      ) : null}
      <div style={{ display: 'flex', gap: 8, marginTop: 'auto', flexWrap: 'wrap', alignItems: 'center' }}>
        {siteUrl ? (
          <a href={siteUrl} target="_blank" rel="noopener noreferrer" className="btn" style={{ fontSize: 12.5, fontWeight: 600, borderRadius: 9, padding: '7px 12px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 5, background: 'var(--bb-indigo)', color: '#fff' }}>
            ↗ Сайт
          </a>
        ) : null}
        {p.caseUrl ? (
          <a href={p.caseUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12.5, fontWeight: 600, borderRadius: 9, padding: '7px 12px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 5, background: 'var(--bb-violet-soft)', color: 'var(--bb-violet)' }}>
            📄 Кейс <ExternalLink size={12} />
          </a>
        ) : (
          <span style={{ fontSize: 11, color: 'var(--bb-faint)' }}>кейс на сайте не опубликован</span>
        )}
      </div>
    </div>
  );
}

export function PortfolioView({ data }: { data: PortfolioData }) {
  const [niche, setNiche] = useState<string | null>(null);
  const [service, setService] = useState<string | null>(null);
  const [onlyWithCase, setOnlyWithCase] = useState(false);
  const [query, setQuery] = useState('');
  const [showAllNiches, setShowAllNiches] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const filtered = useMemo(
    () => filterProjects(data.projects, { niche, service, onlyWithCase, query }),
    [data.projects, niche, service, onlyWithCase, query],
  );
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
            <div className="pf-grid">
              {filtered.slice(0, limit).map((p) => <CaseCard key={p.project} p={p} />)}
            </div>
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
