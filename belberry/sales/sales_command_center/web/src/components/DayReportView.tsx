'use client';

import { useRef, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { ru } from 'date-fns/locale';
import { ArrowLeft, ChevronLeft, ChevronRight, Printer, ExternalLink, Calendar, FileText } from 'lucide-react';
import { CalendarView } from '@/components/CalendarView';

function label(date: string): string {
  try {
    return format(parseISO(date), 'd MMMM yyyy', { locale: ru });
  } catch {
    return date;
  }
}

interface TigerLeader { name: string; count: number }
interface TigerStats { monthLabel: string; days: number; leaders: TigerLeader[] }
const MEDALS = ['🥇', '🥈', '🥉'];

function TigerBoard({ tigers }: { tigers?: TigerStats }) {
  if (!tigers || tigers.leaders.length === 0) {
    return (
      <div className="bb-card bb-tiger-board">
        <div className="bb-sect-head"><span className="bb-sect-ic">🐅</span><h2>Тигры месяца</h2></div>
        <p style={{ color: 'var(--bb-muted)', fontSize: 13 }}>Пока нет данных за месяц.</p>
      </div>
    );
  }
  const max = tigers.leaders[0].count || 1;
  return (
    <div className="bb-card bb-tiger-board">
      <div className="bb-sect-head"><span className="bb-sect-ic">🐅</span><h2>Тигры месяца</h2><small>{tigers.monthLabel} · {tigers.days} дн.</small></div>
      <ul className="bb-tiger-list">
        {tigers.leaders.map((l, i) => (
          <li key={l.name}>
            <span className="bb-tiger-rank">{MEDALS[i] ?? `${i + 1}.`}</span>
            <span className="bb-tiger-name">{l.name}</span>
            <span className="bb-tiger-bar"><i style={{ width: `${Math.max(8, (l.count / max) * 100)}%` }} /></span>
            <span className="bb-tiger-cnt tabular">{l.count}×</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DayReportView({ availableDates, initialDate, tigers }: { availableDates: string[]; initialDate?: string; tigers?: TigerStats }) {
  // availableDates отсортированы desc (свежие сверху).
  const [selected, setSelected] = useState<string | null>(initialDate ?? null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  if (!selected) {
    const latest = availableDates[0];
    return (
      <div className="bb-archive-grid">
        <div className="bb-card">
          {latest ? (
            <button className="bb-rbtn" style={{ marginBottom: 16 }} onClick={() => setSelected(latest)}>
              <FileText size={15} /> Открыть последний отчёт · {label(latest)}
            </button>
          ) : null}
          <CalendarView availableDates={availableDates} onSelect={setSelected} />
        </div>
        <TigerBoard tigers={tigers} />
      </div>
    );
  }

  const idx = availableDates.indexOf(selected);
  const newer = idx > 0 ? availableDates[idx - 1] : null; // более свежий день
  const older = idx >= 0 && idx < availableDates.length - 1 ? availableDates[idx + 1] : null;

  function printReport() {
    frameRef.current?.contentWindow?.print();
  }

  return (
    <div className="bb-fade">
      <div className="bb-rtoolbar">
        <button className="bb-rbtn" onClick={() => setSelected(null)}>
          <ArrowLeft size={15} /> Архив
        </button>
        <button className="bb-rnav" disabled={!older} onClick={() => older && setSelected(older)} aria-label="Предыдущий день">
          <ChevronLeft size={16} />
        </button>
        <span className="bb-rtitle">
          <Calendar size={16} /> {label(selected)}
        </span>
        <button className="bb-rnav" disabled={!newer} onClick={() => newer && setSelected(newer)} aria-label="Следующий день">
          <ChevronRight size={16} />
        </button>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="bb-rbtn" onClick={printReport}>
            <Printer size={15} /> Печать
          </button>
          <a className="bb-rbtn" href={`/day/${selected}`} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={15} /> В новой вкладке
          </a>
        </div>
      </div>
      <div className="bb-rframe-wrap">
        <iframe ref={frameRef} className="bb-rframe" src={`/day/${selected}`} title={`Отчёт за ${label(selected)}`} />
      </div>
    </div>
  );
}
