// Full AI read for one story: impact, headline, gist, affected tickers with live prices,
// bull/bear, cross-market ripple, historical analog, confidence and sources.
import { useStory } from '@/data/queries';
import { useUi } from '@/data/ui';
import { useLive } from '@/data/live';
import { useT } from '@/i18n';
import { dirColor, dateTime, fmt, priceDigits } from '@/lib/format';
import { Chg, Empty, Label, Loading, MktTag } from './ui';
import type { WireEvent } from '@/lib/types';

/** Headline in the UI language: the AI translation when present, else the original wording. */
export function eventTitle(e: WireEvent, bi: (b: { en: string; zh: string } | null | undefined, f?: string) => string) {
  const ai = e.ai?.title;
  return ai && (ai.en || ai.zh) ? bi(ai, e.title) : e.title;
}

export function AIRead({ storyId }: { storyId: string | null }) {
  const { t, bi, lang } = useT();
  const set = useUi((s) => s.set);
  const upDown = useUi((s) => s.upDown);
  const liveQ = useLive((s) => s.quotes);
  const { data: st, isLoading, error } = useStory(storyId);
  if (!storyId) return <Empty>{t('Select an item from the wire or Need to know.')}</Empty>;
  if (isLoading) return <Loading />;
  if (error || !st) return <Empty>{t('No data from any source.')}</Empty>;
  const lead = st.events.find((e) => e.state === 'done') || st.events[0];
  const r = st.read;
  const impact = st.impact ?? lead?.impact ?? null;
  const mkt = st.mkts[0];
  const openCo = (id: string) => (id.startsWith('IX:') ? set({ view: 'market', indexId: id }) : set({ view: 'company', companyId: id }));
  const affected = r?.affected?.length ? r.affected : st.symbols.map((id) => ({ id, dir: lead?.ai?.dirs?.[id] ?? 0, note: { en: '', zh: '' } }));
  return (
    <div className="flex flex-col gap-3.5">
      <div className="font-mono text-[0.8125rem] text-dim">
        {t('AI read')} {dateTime(lead?.ts || st.lastSeen, lang)} · {st.mkts.map((m) => t(m)).join(' · ')}
      </div>
      <div className="flex gap-4 items-start">
        {impact != null && (
          <div className="flex-none flex flex-col gap-[5px] w-16">
            <div className="font-mono text-[1.875rem] leading-none">{impact}<span className="text-[0.875rem] text-faint">/10</span></div>
            <div className="flex gap-[2px]">
              {Array.from({ length: 10 }, (_, i) => (
                <div key={i} className="flex-1 h-1" style={{ background: i < impact ? 'var(--amber)' : 'rgb(var(--line))' }} />
              ))}
            </div>
          </div>
        )}
        <div className="text-[1.1875rem] font-medium leading-[1.3]">{lead ? eventTitle(lead, bi) : st.headline}</div>
      </div>
      {lead?.ai?.comment && (
        <div className="border-l-2 border-sky pl-3 text-[0.9688rem] leading-[1.55]">{bi(lead.ai.comment)}</div>
      )}
      {!lead?.ai && lead?.body && <p className="m-0 text-[0.9375rem] leading-[1.6] text-muted">{lead.body.slice(0, 600)}</p>}

      {st.readState === 'pending' && <div className="text-[0.875rem] text-faint animate-pulse">{t('Generating the AI read…')}</div>}
      {st.readState === 'disabled' && <div className="text-[0.875rem] text-faint">{t('AI reads are off: add GLM_API_KEY to .env')}</div>}

      {r && <p className="m-0 text-[0.9375rem] leading-[1.6] text-muted">{bi(r.simple)}</p>}
      {r && bi(r.detail) && <p className="m-0 text-[0.9375rem] leading-[1.6] text-muted">{bi(r.detail)}</p>}

      {affected.length > 0 && (
        <div className="border border-line rounded-[2px] overflow-hidden">
          {affected.map((a) => {
            const q = liveQ[a.id] || st.quotes[a.id];
            return (
              <button key={a.id} onClick={() => openCo(a.id)}
                className="grid grid-cols-[80px_minmax(0,1fr)_80px_64px_64px] gap-2.5 items-center w-full text-left border-0 border-b border-line2 bg-transparent px-3 py-2 text-[0.9062rem] text-ink cursor-pointer hover:bg-hover">
                <span className="font-mono">{q?.ticker || a.id.split(':').pop()}</span>
                <span className="truncate" title={bi(a.note)}>{(lang === 'zh' ? q?.nameZh || q?.name : q?.name || q?.nameZh) || ''}{bi(a.note) ? <span className="text-faint"> · {bi(a.note)}</span> : null}</span>
                <span className="font-mono text-right">{q?.price != null ? fmt(q.price, priceDigits(q.price)) : '—'}</span>
                <span className="text-right"><Chg v={q?.pct} mkt={q?.mkt} /></span>
                <span className="font-mono text-[0.8125rem] text-right" style={{ color: dirColor(a.dir, q?.mkt, upDown) }}>
                  {a.dir > 0 ? t('▲ Positive') : a.dir < 0 ? t('▼ Negative') : t('— Mixed')}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {r && (
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-line rounded-[2px] px-3 py-2.5 flex flex-col gap-[5px]">
            <span className="font-mono text-[0.75rem] tracking-[.08em]" style={{ color: dirColor(1, mkt, upDown) }}>{t('BULL CASE')}</span>
            <span className="text-[0.9062rem] leading-[1.5]">{bi(r.bull)}</span>
          </div>
          <div className="border border-line rounded-[2px] px-3 py-2.5 flex flex-col gap-[5px]">
            <span className="font-mono text-[0.75rem] tracking-[.08em]" style={{ color: dirColor(-1, mkt, upDown) }}>{t('BEAR CASE')}</span>
            <span className="text-[0.9062rem] leading-[1.5]">{bi(r.bear)}</span>
          </div>
        </div>
      )}

      {r && r.ripple.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <Label>{t('Cross-market ripple')}</Label>
          {r.ripple.map((rp, i) => (
            <div key={i} className="grid grid-cols-[18px_140px_minmax(0,1fr)] gap-2 items-baseline text-[0.9062rem] leading-[1.45]">
              <span className="font-mono text-[0.75rem] text-amber">{i + 1}</span>
              <span className="font-mono text-[0.8125rem] text-muted">{bi(rp.where)}</span>
              <span>{bi(rp.text)}</span>
            </div>
          ))}
        </div>
      )}

      {r && (
        <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-2">
          <div className="border border-dashed border-edge rounded-[2px] px-3 py-2.5 flex flex-col gap-1">
            <Label>{t('Historical analog')}</Label>
            {r.analog ? (<><span className="text-[0.9375rem] font-medium">{bi(r.analog.title)}</span><span className="text-[0.9062rem] leading-[1.5] text-muted">{bi(r.analog.text)}</span></>)
              : <span className="text-[0.875rem] text-faint">—</span>}
          </div>
          <div className="border border-line rounded-[2px] px-3 py-2.5 flex flex-col gap-1.5">
            <div className="flex justify-between items-baseline">
              <Label>{t('Confidence')}</Label>
              <span className="font-mono text-[1.25rem]">{r.confidence ?? '—'}{r.confidence != null && '%'}</span>
            </div>
            <span className="text-[0.875rem] text-muted">{bi(r.horizon)}</span>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Label>{t('Sources')}</Label>
        {st.events.slice(0, 6).map((e) => (
          <a key={e.id} href={e.url || undefined} target="_blank" rel="noreferrer" className="text-[0.875rem] text-sky no-underline hover:underline truncate">
            <MktTag mkt={e.source} /> {e.title}
          </a>
        ))}
        {st.readMeta && <span className="font-mono text-[0.75rem] text-faint">{st.readMeta.model} · {st.readMeta.promptVersion}</span>}
      </div>
    </div>
  );
}
