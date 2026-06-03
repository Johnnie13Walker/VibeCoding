'use client';

import { useRef, useState } from 'react';
import { format, parseISO } from 'date-fns';
import { ru } from 'date-fns/locale';
import { ArrowLeft, ChevronLeft, ChevronRight, Printer, ExternalLink, Calendar } from 'lucide-react';
import { CalendarView } from '@/components/CalendarView';

function label(date: string): string {
  try {
    return format(parseISO(date), 'd MMMM yyyy', { locale: ru });
  } catch {
    return date;
  }
}

export function DayReportView({ availableDates }: { availableDates: string[] }) {
  // availableDates отсортированы desc (свежие сверху).
  const [selected, setSelected] = useState<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  if (!selected) {
    return <CalendarView availableDates={availableDates} onSelect={setSelected} />;
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
