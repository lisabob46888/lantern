import { useEffect, useState } from 'react';
import { useSearch } from '@/data/queries';
import { useT } from '@/i18n';
import type { Quote } from '@/lib/types';

/** Ticker / name / pinyin search across US, CN and HK (Tencent smartbox, Finnhub fallback). */
export function SearchBox({ onPick, placeholder, dashed = false, autoFocus = false }: {
  onPick: (s: Quote) => void; placeholder?: string; dashed?: boolean; autoFocus?: boolean;
}) {
  const { t, lang } = useT();
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(q), 250);
    return () => clearTimeout(h);
  }, [q]);
  const { data, isFetching } = useSearch(debounced);
  const pick = (s: Quote) => {
    onPick(s);
    setQ('');
    setOpen(false);
  };
  return (
    <div className="relative w-full">
      <input
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onKeyDown={(e) => { if (e.key === 'Enter' && data?.[0]) pick(data[0]); if (e.key === 'Escape') setOpen(false); }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder ?? 'NVDA · 0700 · 茅台'}
        className={`w-full bg-panel rounded-[2px] px-2.5 py-[6px] font-mono text-[0.875rem] text-ink outline-none ${dashed ? 'border border-dashed border-edge' : 'border border-edge'}`}
      />
      {open && debounced && (
        <div className="absolute top-[34px] left-0 w-[320px] max-h-[360px] overflow-auto bg-panel border border-edge rounded-[3px] shadow-[0_8px_24px_var(--shadow)] z-50">
          {isFetching && !data && <div className="px-3 py-2 text-[0.875rem] text-faint">{t('Loading…')}</div>}
          {data?.length === 0 && <div className="px-3 py-2 text-[0.875rem] text-faint">{t('No data from any source.')}</div>}
          {data?.map((r) => (
            <button key={r.id} onMouseDown={() => pick(r)}
              className="flex w-full gap-2.5 items-center border-0 bg-transparent px-2.5 py-[7px] cursor-pointer text-left hover:bg-chip">
              <span className="font-mono text-[0.875rem] w-[72px] text-ink">{r.ticker}</span>
              <span className="flex-1 text-[0.875rem] text-ink truncate">{lang === 'zh' ? r.nameZh || r.name : r.name || r.nameZh}</span>
              <span className="font-mono text-[0.75rem] text-dim">{t(r.mkt)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
