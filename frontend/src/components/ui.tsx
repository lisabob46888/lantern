import type { ReactNode } from 'react';
import { useT } from '@/i18n';
import { useUi } from '@/data/ui';
import { dirColor } from '@/lib/format';
import type { Mkt } from '@/lib/types';

export function Panel({ title, right, children, className = '', bodyClass = '' }: {
  title: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={`bg-panel flex flex-col min-w-0 ${className}`}>
      <div className="min-h-[32px] flex-none flex items-center justify-between pr-2.5 bg-bar border-b border-line">
        <span className="font-mono text-[0.8125rem] font-medium tracking-[.08em] uppercase pl-3 text-ink border-l-2 border-amber h-full flex items-center">
          {title}
        </span>
        <div className="flex items-center gap-2 font-mono text-[0.75rem] text-dim">{right}</div>
      </div>
      <div className={`flex-1 overflow-auto ${bodyClass}`}>{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-6 text-[0.9375rem] text-dim">{children}</div>;
}

export function Loading() {
  const { t } = useT();
  return <div className="px-4 py-6 text-[0.9375rem] text-faint animate-pulse">{t('Loading…')}</div>;
}

export function MktTag({ mkt }: { mkt: string }) {
  const { t } = useT();
  return <span className="border border-edge px-[5px] rounded-[3px] text-muted font-mono text-[0.75rem]">{t(mkt)}</span>;
}

export function ImpactTag({ impact }: { impact: number | null }) {
  const { t } = useT();
  if (impact == null) return null;
  const color = impact >= 8 ? 'var(--red)' : impact >= 6 ? 'var(--amber)' : 'rgb(var(--dim))';
  return <span className="font-mono text-[0.75rem]" style={{ color }}>{t('IMPACT')} {impact}</span>;
}

export function Chg({ v, mkt, d = 2 }: { v: number | null | undefined; mkt?: Mkt; d?: number }) {
  const upDown = useUi((s) => s.upDown);
  if (v == null) return <span className="text-faint">—</span>;
  return (
    <span className="font-mono" style={{ color: dirColor(Math.sign(v), mkt, upDown) }}>
      {(v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d)}%
    </span>
  );
}

export function SourceNote({ source, fetchedAt }: { source?: string | null; fetchedAt?: number }) {
  const { t } = useT();
  if (!source) return null;
  return (
    <span className="font-mono text-[0.75rem] text-faint" title={fetchedAt ? new Date(fetchedAt).toLocaleString() : ''}>
      {t('Source')}: {source}
    </span>
  );
}

export function Tabs<T extends string>({ items, value, onChange }: {
  items: { id: T; label: string }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="flex bg-chip rounded-[2px] p-[2px] gap-[2px]">
      {items.map((it) => (
        <button key={it.id} onClick={() => onChange(it.id)}
          className={`border-0 px-2.5 py-[3px] rounded-[2px] font-mono text-[0.8125rem] tracking-[.04em] uppercase cursor-pointer ${value === it.id ? 'bg-ink text-page' : 'bg-transparent text-ink'}`}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[0.75rem] tracking-[.08em] uppercase text-dim">{children}</span>;
}
