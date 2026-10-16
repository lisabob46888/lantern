// Index page — prototype layout: sidebar of indices, header + 4 stats, "What this index tracks",
// tabs JOURNEY (chart + major events beside the AI read) and MARKET ANALYSIS (post-market report).
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useBars, useLists, usePostMarket, usePutList, useQuote, useQuotes, useSecEvents, useSessions } from '@/data/queries';
import { api } from '@/data/api';
import { useLive } from '@/data/live';
import { useUi } from '@/data/ui';
import { useT } from '@/i18n';
import { dayShort, dirColor, fmt, priceDigits } from '@/lib/format';
import { CandleChart, toItems, type ChartItem } from '@/components/CandleChart';
import { eventTitle } from '@/components/AIRead';
import { StoryCard } from '@/components/StoryCard';
import { Badge, Card, EventRow, Muted, Note, PageHeader, ResearchLayout, Section, SideList, SideRow, StatGrid, UTabs } from '@/components/page';
import { Chg, SourceNote } from '@/components/ui';
import type { Bi, Bar, Mkt } from '@/lib/types';

export const RANGES = ['1D', '1M', '6M', '1Y', '5Y'] as const;

/** Chart card: range pills + performance on the right, candles with event labels, hint line. */
export function ChartCard({ bars, unit, mkt, items, selected, onSelect, range, ranges, setRange, perfNote, hint, source, log }: {
  bars: Bar[]; unit: string; mkt: Mkt; items: ChartItem[]; selected: string | null; onSelect: (k: string) => void;
  range: string; ranges: { id: string; label: string }[]; setRange: (r: string) => void; perfNote?: React.ReactNode; hint: string;
  source?: string | null; log?: boolean;
}) {
  const { t } = useT();
  const perf = bars.length > 1 ? (bars[bars.length - 1].c / bars[0].o - 1) * 100 : null;
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-1">
          {ranges.map((r) => (
            <button key={r.id} onClick={() => setRange(r.id)}
              className={`border-0 rounded-[2px] px-2.5 py-1 font-mono text-[0.8125rem] cursor-pointer ${range === r.id ? 'bg-ink text-page' : 'bg-transparent text-dim hover:text-ink'}`}>{r.label}</button>
          ))}
        </div>
        <span className="font-mono text-[0.875rem]">{perfNote ?? (perf != null && <><Chg v={perf} mkt={mkt} /> <span className="text-dim">{t('over')} {range}</span></>)}</span>
      </div>
      {bars.length ? <CandleChart bars={bars} unit={unit} mkt={mkt} items={items} selected={selected} onSelect={onSelect} log={log} />
        : <Muted>{t('Loading…')}</Muted>}
      <div className="flex justify-between gap-4 text-[0.8125rem] text-faint"><span>{hint}</span><SourceNote source={source} /></div>
    </Card>
  );
}

function IndexSidebar({ id, onSelect }: { id: string | null; onSelect: (x: string) => void }) {
  const { t, lang } = useT();
  const market = useUi((s) => s.market);
  const { data: lists } = useLists();
  const put = usePutList();
  const [editing, setEditing] = useState(false);
  const all = lists?.ix || [];
  const ids = all.filter((x) => market === 'ALL' || x.split(':')[1] === market);
  const { data: snap } = useQuotes(ids);
  const live = useLive((s) => s.quotes);
  return (
    <SideList title={t('My indices')} count={ids.length} editing={editing} setEditing={setEditing} addKind="index"
      onAdd={(q) => !all.includes(q.id) && put.mutate({ name: 'ix', items: [...all, q.id] })}>
      {ids.map((x) => {
        const q = live[x] || snap?.[x];
        return (
          <SideRow key={x} name={q ? (lang === 'zh' ? q.nameZh || q.name : q.name) : x} sub={`${q?.ticker || x.split(':')[2]} · ${t(x.split(':')[1])}`}
            price={q?.price != null ? fmt(q.price) : null} chg={q?.pct} mkt={q?.mkt} selected={x === id} editing={editing}
            onClick={() => onSelect(x)} onRemove={() => put.mutate({ name: 'ix', items: all.filter((y) => y !== x) })} />
        );
      })}
    </SideList>
  );
}

function Journey({ id, mkt }: { id: string; mkt: Mkt }) {
  const { t, bi, lang } = useT();
  const [range, setRange] = useState('6M');
  const { data: bars } = useBars(id, range);
  const { data: events } = useSecEvents(id);
  const items = useMemo(() => toItems(events || [], mkt, id), [events, mkt, id]);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => setSel(null), [id]);
  const rows = bars?.bars || [];
  const first = rows[0]?.t.slice(0, 10), last = rows[rows.length - 1]?.t.slice(0, 10);
  const current = items.find((i) => i.key === sel) || items[0];
  return (
    <>
      <ChartCard bars={rows} unit={bars?.unit || 'd'} mkt={mkt} items={items} selected={current?.key || null} onSelect={setSel}
        range={range} ranges={RANGES.map((r) => ({ id: r, label: r }))} setRange={setRange} source={bars?.source}
        hint={t('Labels N1, N2… mark news on the candle where it hit. Label colour shows the expected direction. Click a label for details.')} />
      <Section title={t('Major events')}>
        {items.length ? (
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-5 mt-2 items-start">
            <div className="flex flex-col">
              {items.slice(0, 12).map((it) => {
                const outside = first && last && range !== '1D' && (it.date < first || it.date > last);
                return (
                  <EventRow key={it.key} badge={<Badge label={it.label} dir={it.dir} mkt={mkt} />} title={eventTitle(it.ev!, bi)}
                    meta={<>{dayShort(it.date, lang)} &nbsp;{t('impact')} {it.ev?.impact ?? '—'}{outside ? ` · ${t('outside')} ${range}` : ''}</>}
                    selected={current?.key === it.key} onClick={() => setSel(it.key)} />
                );
              })}
            </div>
            <Card><StoryCard storyId={current?.ev?.storyId || null} label={current?.label} dir={current?.dir} mkt={mkt} /></Card>
          </div>
        ) : <Muted>{t('No data from any source.')}</Muted>}
      </Section>
    </>
  );
}

function MarketAnalysis({ mkt }: { mkt: Mkt }) {
  const { t, bi, lang } = useT();
  const upDown = useUi((s) => s.upDown);
  const { data: sessions } = useSessions();
  const s = sessions?.find((x) => x.mkt === mkt);
  const done = (s?.tradingDays || []).filter((d) => s?.lastCompleted && d <= s.lastCompleted).slice(-6).reverse();
  const [day, setDay] = useState<string | null>(null);
  useEffect(() => setDay(null), [mkt]);
  const { data: pm } = usePostMarket(mkt, day);
  const r = pm as Record<string, any> | undefined;
  const b2 = (o: any, k: string): Bi => ({ en: o?.[`${k}_en`] || '', zh: o?.[`${k}_zh`] || '' });
  const active = day || done[0];
  return (
    <Card className="!p-0">
      <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b border-line">
        <span className="font-mono text-[0.75rem] tracking-[.08em] uppercase text-dim mr-1">{t('Trade date')}</span>
        {done.map((d, i) => (
          <button key={d} onClick={() => setDay(d)}
            className={`border rounded-[3px] px-3 py-1 text-[0.875rem] cursor-pointer ${active === d ? 'bg-ink text-page border-ink' : 'bg-transparent text-ink border-edge'}`}>
            {i === 0 ? t('Latest') : new Date(d + 'T12:00:00Z').toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })}
          </button>
        ))}
        <input type="date" value={active || ''} max={done[0]} onChange={(e) => e.target.value && setDay(e.target.value)}
          className="bg-panel border border-edge rounded-[3px] text-ink px-2 py-1 font-mono text-[0.875rem]" />
      </div>
      <div className="p-5 flex flex-col gap-5">
        {!r && <Muted>{t('Loading…')}</Muted>}
        {r && r.status === 'pending' && <Muted>{t('Report pending — it publishes after the close.')} ({r.published})</Muted>}
        {r && r.status !== 'pending' && (
          <>
            <div className="font-mono text-[0.8125rem] text-dim">{t('POST-MARKET')} · {t(mkt)} · {dayShort(r.tradeDate, lang)} · {t('published')} {r.published}</div>
            {r.ai ? <div className="text-[1.375rem] font-medium leading-[1.3] -mt-2">{bi(b2(r.ai, 'headline'))}</div>
              : <div className="text-[0.875rem] text-faint">{t('Session data only — AI analysis unavailable.')}</div>}
            {(r.indices || []).length > 0 && (
              <StatGrid cols={Math.min(4, r.indices.length)} items={r.indices.map((ix: any) => ({
                k: lang === 'zh' ? ix.nameZh : ix.name, v: fmt(ix.close), hint: <Chg v={ix.pct} mkt={mkt} />,
              }))} />
            )}
            {r.breadth && (
              <div className="flex items-center gap-3 text-[0.875rem]">
                <span className="font-mono" style={{ color: dirColor(1, mkt, upDown) }}>{r.breadth.up} {t('advancers')}</span>
                <div className="flex-1 h-2 flex rounded-sm overflow-hidden bg-line">
                  <div style={{ width: `${(r.breadth.up / ((r.breadth.up || 0) + (r.breadth.down || 0) || 1)) * 100}%`, background: dirColor(1, mkt, upDown) }} />
                  <div className="flex-1" style={{ background: dirColor(-1, mkt, upDown) }} />
                </div>
                <span className="font-mono" style={{ color: dirColor(-1, mkt, upDown) }}>{r.breadth.down} {t('decliners')}</span>
              </div>
            )}
            {r.ai && <Note label={t('AI session analysis')}><p className="m-0">{bi(b2(r.ai, 'summary'))}</p></Note>}
            <div className="grid grid-cols-2 gap-6">
              {r.ai?.drivers?.length > 0 && (
                <Section title={t('What drove the session')}>
                  {r.ai.drivers.map((d: any, i: number) => (
                    <div key={i} className="grid grid-cols-[2em_minmax(0,1fr)] py-2 border-b border-line text-[0.9375rem]">
                      <span className="font-mono text-faint">{String(i + 1).padStart(2, '0')}</span>
                      <span><span className="font-medium">{bi(b2(d, 'k'))}</span><br /><span className="text-muted text-[0.875rem]">{bi(b2(d, 'v'))}</span></span>
                    </div>
                  ))}
                </Section>
              )}
              {r.sectors?.length > 0 && (
                <Section title={t('Sector performance')}>
                  {r.sectors.slice(0, 8).map((sx: any) => <div key={sx.name} className="flex justify-between py-1.5 border-b border-line text-[0.9375rem]"><span>{sx.name}</span><Chg v={sx.pct} mkt={mkt} /></div>)}
                </Section>
              )}
              {r.movers?.length > 0 && (
                <Section title={t('Notable movers')}>
                  {r.movers.map((m: any) => <div key={m.id} className="flex justify-between py-1.5 border-b border-line text-[0.9375rem]"><span><span className="font-mono">{m.ticker}</span> <span className="text-muted">{m.name}</span></span><Chg v={m.pct} mkt={mkt} /></div>)}
                </Section>
              )}
              {r.ai?.watch?.length > 0 && (
                <Section title={t('Watch next')}>
                  {r.ai.watch.map((w: any, i: number) => <div key={i} className="py-2 border-b border-line text-[0.9375rem]"><span className="font-medium">{bi(b2(w, 'k'))}</span> — <span className="text-muted">{bi(b2(w, 'v'))}</span></div>)}
                </Section>
              )}
            </div>
            {r.ai?.stance && (
              <Card className="flex flex-col gap-1">
                <span className="text-[0.75rem] font-semibold tracking-[.08em] uppercase text-sky">{t('AI outlook · next session')}</span>
                <span className="font-mono text-amber uppercase">{t(r.ai.stance)}</span>
                <span className="text-[0.9375rem] text-muted">{bi(b2(r.ai, 'stance_text'))}</span>
                {r.ai.confidence != null && <span className="font-mono text-[0.75rem] text-faint">{t('confidence')} {r.ai.confidence}%</span>}
              </Card>
            )}
            {r.missing?.length > 0 && <div className="font-mono text-[0.75rem] text-faint">{t('Missing')}: {r.missing.join(' · ')}</div>}
            <div className="font-mono text-[0.75rem] text-faint">{t('Sources')}: {[...new Set(r.sources || [])].join(', ')}{r.model ? ` · ${r.model}` : ''}</div>
          </>
        )}
      </div>
    </Card>
  );
}

export function Market() {
  const { t, bi, lang } = useT();
  const { indexId, market, set } = useUi();
  const { data: lists } = useLists();
  const first = (lists?.ix || []).find((x) => market === 'ALL' || x.split(':')[1] === market) || null;
  const id = indexId && (market === 'ALL' || indexId.split(':')[1] === market) ? indexId : first;
  const { data: q0 } = useQuote(id);
  const live = useLive((s) => (id ? s.quotes[id] : undefined));
  const q = live ? { ...q0, ...live } : q0;
  const mkt = (id?.split(':')[1] || 'US') as Mkt;
  const { data: prof } = useQuery({ queryKey: ['ixprof', id], queryFn: () => api.get<any>(`/indices/${encodeURIComponent(id || '')}/profile`), enabled: !!id, staleTime: 3600_000 });
  const [tab, setTab] = useState<'journey' | 'analysis'>('journey');
  const range52 = prof?.lo52 != null && prof?.hi52 != null && q?.price != null ? Math.round(((q.price - prof.lo52) / (prof.hi52 - prof.lo52 || 1)) * 100) : null;
  return (
    <ResearchLayout sidebar={<IndexSidebar id={id} onSelect={(x) => set({ indexId: x })} />}>
      {!id && <Muted>{t('Your list is empty. Use + ADD to pick items.')}</Muted>}
      {id && q && (
        <>
          <PageHeader meta={`${q.ticker} · ${prof?.exchange || ''} · ${t(mkt)}`} title={lang === 'zh' ? q.nameZh : q.name}
            sub={lang === 'zh' ? q.name : q.nameZh} price={fmt(q.price, priceDigits(q.price))} chg={q.pct} mkt={mkt} chgNote={t('today')} />
          <StatGrid items={[
            { k: t('Prev close'), v: fmt(q.prevClose), hint: t('Last session') },
            { k: t('Day change'), v: q.chg != null ? (q.chg > 0 ? '+' : '') + fmt(q.chg) : '—', hint: t('Points') },
            { k: t('52-week range'), v: prof?.lo52 != null ? `${fmt(prof.lo52, 0)}–${fmt(prof.hi52, 0)}` : '—', hint: range52 != null ? `${range52}% ${t('of range')}` : undefined },
            { k: t('Constituents'), v: prof?.about?.members || '—', hint: prof?.about?.members ? `${prof.exchange} ${t('listed')}` : undefined },
          ]} />
          {prof?.about?.desc && (
            <Note label={t('What this index tracks')}>
              <p className="m-0">{bi(prof.about.desc)}</p>
              {prof.about.url && <a href={prof.about.url} target="_blank" rel="noreferrer" className="text-[0.8125rem]">{t('Source')}</a>}
            </Note>
          )}
          <UTabs items={[{ id: 'journey', label: t('Journey') }, { id: 'analysis', label: t('Market analysis') }]} value={tab} onChange={setTab} />
          {tab === 'journey' ? <Journey id={id} mkt={mkt} /> : <MarketAnalysis mkt={mkt} />}
        </>
      )}
    </ResearchLayout>
  );
}
