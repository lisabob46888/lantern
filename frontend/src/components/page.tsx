// Layout pieces shared by the Index, Companies and Industries pages (the prototype's research layout):
// a 240px list sidebar, then a content column that fills the window (capped at 1440px on very wide screens).
import { useState, type ReactNode } from 'react';
import { useT } from '@/i18n';
import { useUi } from '@/data/ui';
import { dirColor } from '@/lib/format';
import { SearchBox } from './SearchBox';
import type { Mkt, Quote } from '@/lib/types';

export function ResearchLayout({ sidebar, children }: { sidebar: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-full bg-page">
      <aside className="w-[240px] flex-none border-r border-line bg-page">{sidebar}</aside>
      <main className="flex-1 min-w-0 px-8 py-7">
        <div className="max-w-[1440px] flex flex-col gap-7">{children}</div>
      </main>
    </div>
  );
}

/** Sidebar header "MY INDICES 12 [+ ADD] [EDIT]" with an inline search for adding. */
export function SideList({ title, count, editing, setEditing, onAdd, addKind, children }: {
  title: string; count: number; editing: boolean; setEditing: (v: boolean) => void;
  onAdd?: (q: Quote) => void; addKind?: 'index' | 'stock'; children: ReactNode;
}) {
  const { t } = useT();
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <div className="flex items-center justify-between gap-2 px-3.5 h-[44px] border-b border-line">
        <span className="font-mono text-[0.75rem] tracking-[.06em] uppercase text-faint truncate">{title} {count}</span>
        <div className="flex gap-1 flex-none">
          {onAdd && <SmallBtn active={adding} onClick={() => setAdding(!adding)}>{t('+ ADD')}</SmallBtn>}
          <SmallBtn active={editing} onClick={() => setEditing(!editing)}>{editing ? t('Done') : t('EDIT')}</SmallBtn>
        </div>
      </div>
      {adding && onAdd && (
        <div className="p-2.5 border-b border-line">
          <SearchBox dashed autoFocus placeholder={t('ADD TO LIST +')}
            onPick={(q) => { if (!addKind || (q.kind === 'index') === (addKind === 'index')) onAdd(q); setAdding(false); }} />
        </div>
      )}
      {children}
    </div>
  );
}

export function SmallBtn({ children, onClick, active = false }: { children: ReactNode; onClick: () => void; active?: boolean }) {
  return (
    <button onClick={onClick}
      className={`border rounded-[2px] px-1.5 py-[2px] font-mono text-[0.6875rem] uppercase cursor-pointer whitespace-nowrap ${active ? 'border-amber text-amber bg-transparent' : 'border-edge text-ink bg-transparent hover:border-amber'}`}>
      {children}
    </button>
  );
}

/** One sidebar row: name, ticker · market, optional price, change; amber left bar when selected. */
export function SideRow({ name, sub, price, chg, mkt, selected, editing, onClick, onRemove }: {
  name: string; sub: string; price?: string | null; chg: number | null | undefined; mkt?: Mkt;
  selected: boolean; editing: boolean; onClick: () => void; onRemove: () => void;
}) {
  const upDown = useUi((s) => s.upDown);
  return (
    <div onClick={onClick}
      className={`grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center pl-3.5 pr-3 py-3 border-b border-line cursor-pointer border-l-2 ${selected ? 'bg-chip border-l-amber' : 'border-l-transparent hover:bg-hover'}`}>
      <div className="min-w-0">
        <div className="text-[0.9375rem] font-medium leading-tight">{name}</div>
        <div className="font-mono text-[0.75rem] text-faint mt-0.5">{sub}</div>
      </div>
      <div className="flex items-center gap-2">
        <div className="text-right font-mono text-[0.875rem]">
          {price != null && <div>{price}</div>}
          <div style={{ color: dirColor(Math.sign(chg || 0), mkt, upDown) }}>
            {chg != null ? (chg > 0 ? '+' : chg < 0 ? '−' : '') + Math.abs(chg).toFixed(2) + '%' : '—'}
          </div>
        </div>
        {editing && (
          <button onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="border-0 bg-transparent text-faint cursor-pointer text-[1rem] hover:text-ink">×</button>
        )}
      </div>
    </div>
  );
}

/** "NVDA · NASDAQ · Semiconductors" / big name + second name / price + change on the right. */
export function PageHeader({ meta, title, sub, price, chg, mkt, chgNote }: {
  meta: string; title: string; sub?: string; price?: string | null; chg?: number | null; mkt?: Mkt; chgNote?: string;
}) {
  const upDown = useUi((s) => s.upDown);
  return (
    <div className="flex items-start justify-between gap-6">
      <div className="min-w-0">
        <div className="font-mono text-[0.8125rem] tracking-[.04em] text-dim">{meta}</div>
        <h1 className="m-0 mt-1.5 text-[2rem] font-medium leading-tight">
          {title} {sub && <span className="text-faint font-normal">{sub}</span>}
        </h1>
      </div>
      {price != null && (
        <div className="text-right flex-none">
          <div className="font-mono text-[2rem] leading-tight">{price}</div>
          {chg != null && (
            <div className="font-mono text-[0.9375rem]" style={{ color: dirColor(Math.sign(chg), mkt, upDown) }}>
              {(chg > 0 ? '+' : chg < 0 ? '−' : '') + Math.abs(chg).toFixed(2)}% {chgNote}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export interface Stat { k: string; v: ReactNode; hint?: ReactNode; color?: string }

/** Bordered grid of stat cells (prototype: 4 or 5 columns). */
export function StatGrid({ items, cols = 4 }: { items: Stat[]; cols?: number }) {
  return (
    <div className="grid border border-line rounded-[2px] bg-panel" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {items.map((s, i) => (
        <div key={i} className={`px-4 py-3.5 border-line ${(i + 1) % cols ? 'border-r' : ''} ${i >= cols ? 'border-t' : ''}`}>
          <div className="text-[0.75rem] tracking-[.06em] uppercase text-dim">{s.k}</div>
          <div className="font-mono text-[1.125rem] mt-1" style={s.color ? { color: s.color } : undefined}>{s.v ?? '—'}</div>
          {s.hint && <div className="text-[0.75rem] text-faint mt-0.5">{s.hint}</div>}
        </div>
      ))}
    </div>
  );
}

/** Underline tabs: JOURNEY  UPDATES  OVERVIEW … */
export function UTabs<T extends string>({ items, value, onChange }: { items: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-0 border-b border-line overflow-x-auto no-scrollbar">
      {items.map((it) => (
        <button key={it.id} onClick={() => onChange(it.id)}
          className={`border-0 bg-transparent px-0 mr-9 pb-2.5 pt-1 font-mono text-[0.8125rem] tracking-[.08em] uppercase cursor-pointer whitespace-nowrap border-b-2 -mb-px ${value === it.id ? 'text-ink border-amber' : 'text-dim border-transparent hover:text-ink'}`}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Section({ title, right, children, className = '' }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`flex flex-col ${className}`}>
      <div className="flex items-baseline justify-between border-b border-line pb-2 mb-1">
        <h3 className="m-0 text-[0.8125rem] font-semibold tracking-[.08em] uppercase text-muted">{title}</h3>
        {right && <span className="font-mono text-[0.75rem] text-faint">{right}</span>}
      </div>
      {children}
    </section>
  );
}

/** Blue left-border block: "WHAT THIS INDEX TRACKS", "AI READ · …", "AGENT VIEW". */
export function Note({ label, children, tone = 'sky' }: { label: string; children: ReactNode; tone?: 'sky' | 'amber' }) {
  return (
    <div className={`border-l-2 pl-5 py-1 ${tone === 'sky' ? 'border-sky' : 'border-amber'}`}>
      <div className={`text-[0.75rem] font-semibold tracking-[.08em] uppercase mb-2 ${tone === 'sky' ? 'text-sky' : 'text-amber'}`}>{label}</div>
      <div className="text-[1rem] leading-[1.6] flex flex-col gap-2.5 max-w-[80ch]">{children}</div>
    </div>
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`border border-line rounded-[2px] bg-panel p-5 ${className}`}>{children}</div>;
}

/** Event badge (N1, J3…) coloured by expected direction. */
export function Badge({ label, dir, mkt }: { label: string; dir: number; mkt?: Mkt }) {
  const upDown = useUi((s) => s.upDown);
  const c = dirColor(dir, mkt, upDown);
  return <span className="inline-block font-mono text-[0.6875rem] px-1.5 py-[1px] rounded-[2px] border text-center min-w-[2.6em]" style={{ color: c, borderColor: c }}>{label}</span>;
}

/** Left list of events (badge, title, date · extra), selected row highlighted. */
export function EventRow({ badge, title, meta, selected, onClick }: { badge: ReactNode; title: string; meta: ReactNode; selected: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`grid grid-cols-[3.4em_minmax(0,1fr)] gap-3 w-full text-left border-0 border-b border-line px-2 py-3 cursor-pointer text-ink border-l-2 ${selected ? 'bg-chip border-l-sky' : 'bg-transparent border-l-transparent hover:bg-hover'}`}>
      <span className="pt-0.5">{badge}</span>
      <span className="min-w-0">
        <span className="block text-[0.9375rem] leading-[1.4]">{title}</span>
        <span className="block font-mono text-[0.75rem] text-faint mt-1">{meta}</span>
      </span>
    </button>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <div className="text-[0.9375rem] text-faint py-3">{children}</div>;
}
