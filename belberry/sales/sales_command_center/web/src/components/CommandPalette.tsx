'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Calendar, User, Briefcase } from 'lucide-react';

const PORTAL = 'https://belberrycrm.bitrix24.ru';

type Result =
  | { kind: 'day'; key: string; label: string }
  | { kind: 'manager'; key: string; label: string; meta: string; id: number }
  | { kind: 'deal'; key: string; label: string; meta: string; id: number };

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [results, setResults] = useState<Result[]>([]);
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K — открыть/закрыть.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    }
    function onOpen() {
      setOpen(true);
    }
    window.addEventListener('keydown', onKey);
    window.addEventListener('bb-cmdk-open', onOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('bb-cmdk-open', onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
    else {
      setQ('');
      setSel(0);
    }
  }, [open]);

  // Поиск с дебаунсом.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(q)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!d) return;
          const list: Result[] = [
            ...(d.days ?? []).map((x: string) => ({ kind: 'day' as const, key: `day-${x}`, label: x })),
            ...(d.managers ?? []).map((m: { id: number; name: string; role: string }) => ({
              kind: 'manager' as const, key: `mgr-${m.id}`, label: m.name, meta: m.role, id: m.id,
            })),
            ...(d.deals ?? []).map((dl: { id: number; title: string }) => ({
              kind: 'deal' as const, key: `deal-${dl.id}`, label: dl.title, meta: 'сделка', id: dl.id,
            })),
          ];
          setResults(list);
          setSel(0);
        })
        .catch(() => {});
    }, 160);
    return () => clearTimeout(t);
  }, [q, open]);

  const go = useCallback(
    (r: Result) => {
      setOpen(false);
      if (r.kind === 'day') router.push(`/daily?date=${r.key.replace('day-', '')}`);
      else if (r.kind === 'manager') router.push(`/dashboard?m=${r.id}`);
      else window.open(`${PORTAL}/crm/deal/details/${r.id}/`, '_blank', 'noopener');
    },
    [router],
  );

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(results.length - 1, s + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === 'Enter' && results[sel]) { e.preventDefault(); go(results[sel]); }
  }

  if (!open) return null;

  const icon = (k: Result['kind']) => (k === 'day' ? <Calendar size={16} /> : k === 'manager' ? <User size={16} /> : <Briefcase size={16} />);

  return (
    <div className="bb-cmdk-scrim" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
      <div className="bb-cmdk" role="dialog" aria-label="Поиск">
        <div className="bb-cmdk-input">
          <Search size={18} color="#9a9aa0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="День, менеджер, сделка…"
          />
          <kbd className="bb-cmdk-kbd">esc</kbd>
        </div>
        <div className="bb-cmdk-res">
          {results.length === 0 ? (
            <div className="bb-cmdk-empty">Ничего не найдено</div>
          ) : (
            results.map((r, i) => (
              <button
                key={r.key}
                className={`bb-cmdk-item${i === sel ? ' sel' : ''}`}
                onMouseEnter={() => setSel(i)}
                onClick={() => go(r)}
              >
                {icon(r.kind)}
                <span className="bb-cmdk-label">{r.label}</span>
                {'meta' in r && r.meta ? <span className="bb-cmdk-meta">{r.meta}</span> : null}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
