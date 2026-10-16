// Company page — prototype layout: company list sidebar; header + stat grid; tabs JOURNEY (since-listing
// chart with J labels, IPO stats, trend read, major events), UPDATES (news + catalysts beside the AI read),
// OVERVIEW, FINANCIAL (AI read, income & cash flow, DuPont, quality checks), INSTITUTIONAL VIEWS.
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useBars, useCompany, useLists, usePutList, useQuote, useQuotes, useSecEvents } from '@/data/queries';
import { useLive } from '@/data/live';
import { useUi } from '@/data/ui';
import { useT } from '@/i18n';
import { big, dateTime, dayShort, dirColor, fmt, pct, priceDigits } from '@/lib/format';
import { toItems, type ChartItem } from '@/components/CandleChart';
import { eventTitle } from '@/components/AIRead';
import { StoryCard } from '@/components/StoryCard';
import { ChartCard, RANGES } from './Market';
import { Badge, Card, EventRow, Muted, Note, PageHeader, ResearchLayout, Section, SideList, SideRow, StatGrid, UTabs } from '@/components/page';
import { SourceNote } from '@/components/ui';
import type { Bar, Bi, Meta, Mkt, Quote, WireEvent } from '@/lib/types';

type Tab = 'journey' | 'updates' | 'overview' | 'financial' | 'views';
type Fin = { annual: any[]; dupont: any[]; checks: any[]; read: { fin: Bi; dupont: Bi } | null } & Meta;
type Prof = { profile: Record<string, any> } & Meta;
type Views = Record<string, any> & Meta;
type JourneyData = { bars: Bar[]; stats: any; events: any[]; story: { en: string[]; zh: string[] } | null } & Meta;

const pctPlain = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v.toFixed(d)}%`);

function CompanySidebar({ id, onSelect }: { id: string | null; onSelect: (x: string) => void }) {
  const { t, lang } = useT();
  const market = useUi((s) => s.market);
  const { data: lists } = useLists();
  const put = usePutList();
  const [editing, setEditing] = useState(false);
  const all = lists?.co || [];
  const ids = all.filter((x) => market === 'ALL' || x.startsWith(market + ':'));
  const { data: snap } = useQuotes(ids);
  const live = useLive((s) => s.quotes);
  return (
    <SideList title={t('My companies')} count={ids.length} editing={editing} setEditing={setEditing} addKind="stock"
      onAdd={(q) => { if (!all.includes(q.id)) put.mutate({ name: 'co', items: [...all, q.id] }); onSelect(q.id); }}>
      {ids.map((x) => {
        const q = live[x] || snap?.[x];
        return (
          <SideRow key={x} name={q ? (lang === 'zh' ? q.nameZh || q.name : q.name || q.nameZh) : x} sub={`${q?.ticker || x} · ${t(x.split(':')[0])}`}
            chg={q?.pct} mkt={q?.mkt} selected={x === id} editing={editing} onClick={() => onSelect(x)}
            onRemove={() => put.mutate({ name: 'co', items: all.filter((y) => y !== x) })} />
        );
      })}
      {!ids.length && <div className="px-3.5 py-4 text-[0.875rem] text-faint">{t('Your list is empty. Use + ADD to pick items.')}</div>}
    </SideList>
  );
}

// ---------- JOURNEY ----------
function Journey({ id, mkt, prof }: { id: string; mkt: Mkt; prof?: Prof }) {
  const { t, bi, lang } = useT();
  const upDown = useUi((s) => s.upDown);
  const [range, setRange] = useState('IPO');
  const { data: bars } = useBars(id, range === 'IPO' ? '5Y' : range);
  const { data: jr } = useCompany<JourneyData>(id, 'journey');
  const { data: news } = useSecEvents(id);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => setSel(null), [id]);
  const jItems: ChartItem[] = useMemo(() => (jr?.events || []).map((e) => ({
    key: e.label, label: e.label, dir: Math.sign(e.pct ?? 1), date: e.date.slice(0, 10), hm: '12:00',
  })), [jr]);
  const nItems = useMemo(() => toItems(news || [], mkt, id), [news, mkt, id]);
  const isIpo = range === 'IPO';
  const rows = isIpo ? jr?.bars || [] : bars?.bars || [];
  const s = jr?.stats;
  const p = prof?.profile || {};
  const cur = (jr?.events || []).find((e) => e.label === sel) || jr?.events?.[0];
  const story = jr?.story ? (lang === 'zh' ? jr.story.zh : jr.story.en) : null;
  const moveColor = (e: any) => (e.kind === 'listing' ? 'var(--amber)' : dirColor(Math.sign(e.pct || 0), mkt, upDown));
  return (
    <>
      <ChartCard bars={rows} unit={isIpo ? 'm' : bars?.unit || 'd'} mkt={mkt} items={isIpo ? jItems : nItems}
        selected={isIpo ? cur?.label || null : sel} onSelect={setSel} range={range} setRange={setRange} log={isIpo}
        ranges={[...RANGES.map((r) => ({ id: r, label: r })), { id: 'IPO', label: t('Since IPO') }]}
        perfNote={isIpo && s ? <span style={{ color: dirColor(Math.sign(s.totalPct || 0), mkt, upDown) }}>×{fmt(s.multiple, s.multiple < 10 ? 1 : 0)} {t('since')} {s.since.slice(0, 4)} · {t('log scale')}</span> : undefined}
        hint={isIpo ? t('Labels J1, J2… mark the major events listed below. Monthly candles, log scale.') : t('Labels N1, N2… mark news on the candle where it hit. Label colour shows the expected direction. Click a label for details.')}
        source={isIpo ? jr?.source : bars?.source} />
      {s && (
        <StatGrid cols={5} items={[
          { k: t('IPO date'), v: p.ipo ? dayShort(p.ipo, lang) : dayShort(s.since, lang), hint: p.ipo ? p.exchange : t('first bar in source') },
          { k: t('IPO price'), v: p.ipoPrice ? fmt(p.ipoPrice) : '—', hint: p.ipoPrice ? t('offer price') : t('Not available from current sources.') },
          { k: t('Since first bar'), v: `×${fmt(s.multiple, s.multiple < 10 ? 1 : 0)}`, color: dirColor(Math.sign(s.totalPct || 0), mkt, upDown), hint: t('price only') },
          { k: t('Annualised'), v: pct(s.cagrPct, 1), color: dirColor(Math.sign(s.cagrPct || 0), mkt, upDown), hint: `${t('over')} ${s.years} ${t('years')}` },
          { k: t('Worst drawdown'), v: pct(s.worstDrawdown, 0), color: dirColor(-1, mkt, upDown), hint: s.worstDrawdownAt ? `${t('bottom in')} ${s.worstDrawdownAt.slice(0, 4)}` : undefined },
        ]} />
      )}
      {story && story.length > 0 && (
        <Note label={t('AI read · the trend since IPO')}>{story.map((para, i) => <p key={i} className="m-0">{para}</p>)}</Note>
      )}
      {jr?.events?.length ? (
        <Section title={t('Major events')}>
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-5 mt-2 items-start">
            <div>
              {jr.events.map((e) => (
                <EventRow key={e.label} badge={<Badge label={e.label} dir={Math.sign(e.pct ?? 1)} mkt={mkt} />}
                  title={bi(e.title) || (e.kind === 'listing' ? t('First trading data') : e.move)}
                  meta={<>{dayShort(e.date.slice(0, 10), lang)} &nbsp;<span style={{ color: moveColor(e) }}>{e.kind === 'listing' ? 'IPO' : e.move}</span></>}
                  selected={cur?.label === e.label} onClick={() => setSel(e.label)} />
              ))}
            </div>
            {cur && (
              <Card className="flex flex-col gap-3">
                <div className="flex justify-between"><span className="text-[0.75rem] font-semibold tracking-[.08em] uppercase text-sky">{t('AI read')}</span><Badge label={cur.label} dir={Math.sign(cur.pct ?? 1)} mkt={mkt} /></div>
                <div className="text-[1.25rem] font-medium leading-[1.3]">{bi(cur.title) || cur.move}</div>
                <div className="font-mono text-[0.75rem] text-dim pb-3 border-b border-line">{dayShort(cur.date.slice(0, 10), lang)} &nbsp; {t('PRICE REACTION')} <span style={{ color: moveColor(cur) }}>{cur.kind === 'listing' ? 'IPO' : cur.move}</span></div>
                <p className="m-0 text-[0.9375rem] leading-[1.6] text-muted">{bi(cur.read) || t('AI reads are off: add GLM_API_KEY to .env')}</p>
              </Card>
            )}
          </div>
        </Section>
      ) : null}
    </>
  );
}

// ---------- UPDATES ----------
function Updates({ id, mkt }: { id: string; mkt: Mkt }) {
  const { t, bi, lang } = useT();
  const { data: news } = useCompany<{ items: WireEvent[]; catalysts: { id: string; title: string; at: number; source: string; kind: string }[] }>(id, 'news');
  const items = useMemo(() => toItems((news?.items || []).filter((e) => e.state !== 'skipped'), mkt, id), [news, mkt, id]);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => setSel(null), [id]);
  const cur = items.find((i) => i.key === sel) || items[0];
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-6 items-start">
      <div className="flex flex-col gap-6">
        <Section title={t('News moving this stock')}>
          {!news && <Muted>{t('Loading…')}</Muted>}
          {items.slice(0, 15).map((it) => (
            <button key={it.key} onClick={() => setSel(it.key)}
              className={`grid grid-cols-[3.4em_6.5em_minmax(0,1fr)] gap-2.5 w-full text-left border-0 border-b border-line px-1 py-2.5 cursor-pointer text-ink ${cur?.key === it.key ? 'bg-chip' : 'bg-transparent hover:bg-hover'}`}>
              <span><Badge label={it.label} dir={it.dir} mkt={mkt} /></span>
              <span className="font-mono text-[0.75rem] text-dim pt-0.5">{dayShort(it.date, lang)}</span>
              <span className="text-[0.9375rem] leading-[1.4]">{eventTitle(it.ev!, bi)}{it.ev?.impact != null && <span className="text-faint text-[0.75rem] font-mono"> · {t('impact')} {it.ev.impact}</span>}</span>
            </button>
          ))}
          {news && !items.length && <Muted>{t('No recorded news for this stock.')}</Muted>}
        </Section>
        <Section title={t('Catalysts to watch')}>
          {news?.catalysts.map((c) => (
            <div key={c.id} className="flex justify-between items-baseline gap-3 py-2.5 border-b border-line">
              <span className="text-[0.9375rem]">{c.title}</span>
              <span className="text-right flex-none"><span className="block font-mono text-[0.875rem] text-amber">{dateTime(c.at, lang)}</span>
                <span className="block font-mono text-[0.6875rem] tracking-[.06em] uppercase text-faint">{t('Confirmed date')} · {c.source}</span></span>
            </div>
          ))}
          {news && !news.catalysts.length && <Muted>{t('No scheduled events found.')}</Muted>}
        </Section>
      </div>
      <Card><StoryCard storyId={cur?.ev?.storyId || null} label={cur?.label} dir={cur?.dir} mkt={mkt} /></Card>
    </div>
  );
}

// ---------- OVERVIEW ----------
function KV({ k, v, hint }: { k: string; v: ReactNode; hint?: ReactNode }) {
  return <div className="flex justify-between items-baseline gap-3 py-2 border-b border-line text-[0.9375rem]"><span>{k}</span><span className="font-mono">{v}{hint && <span className="text-faint text-[0.75rem] ml-3">{hint}</span>}</span></div>;
}

function Overview({ id, prof, views }: { id: string; prof?: Prof; views?: Views }) {
  const { t, bi, lang } = useT();
  const set = useUi((s) => s.set);
  const { data: holders } = useCompany<Record<string, any> & Meta>(id, 'holders');
  const { data: peers } = useCompany<{ peers: Quote[] } & Meta>(id, 'peers');
  const p = prof?.profile || {};
  const desc = p.descI18n ? bi(p.descI18n) : p.desc;
  const val = views?.valuation || {};
  const facts = [
    [t('Founded'), p.founded], [t('Headquarters'), p.hq], [t('CEO / Chair'), p.ceo],
    [t('Employees'), p.staff ? fmt(+p.staff, 0) : null], [t('Listed'), p.ipo],
  ].filter(([, v]) => v) as [string, string][];
  return (
    <>
      {desc ? <Note label={t('What this company does')}><p className="m-0">{desc}</p>{p.business && <p className="m-0 text-muted text-[0.9375rem]">{p.business}</p>}</Note>
        : <Muted>{t('Not available from current sources.')}</Muted>}
      {facts.length > 0 && (
        <div className="grid border border-line rounded-[2px] bg-panel" style={{ gridTemplateColumns: `repeat(${facts.length}, minmax(0,1fr))` }}>
          {facts.map(([k, v], i) => <div key={k} className={`px-4 py-3 ${i < facts.length - 1 ? 'border-r border-line' : ''}`}><div className="text-[0.75rem] tracking-[.06em] uppercase text-dim">{k}</div><div className="text-[0.9375rem] mt-1">{v}</div></div>)}
        </div>
      )}
      <div className="grid grid-cols-2 gap-8">
        <Section title={t('Valuation')}>
          {Object.keys(val).length ? (
            <>
              {val.forwardPe != null && <KV k={t('Forward P/E')} v={fmt(val.forwardPe, 1)} />}
              {val.trailingPe != null && <KV k={t('Trailing P/E')} v={fmt(val.trailingPe, 1)} />}
              {val.pb != null && <KV k={t('Price / book')} v={fmt(val.pb, 1)} />}
              {val.evEbitda != null && <KV k="EV / EBITDA" v={fmt(val.evEbitda, 1)} />}
              {val.evRevenue != null && <KV k={t('EV / sales')} v={fmt(val.evRevenue, 1)} />}
              {val.peg != null && <KV k="PEG" v={fmt(val.peg, 2)} />}
            </>
          ) : <Muted>{t('Not available from current sources.')}</Muted>}
        </Section>
        <Section title={t('Major shareholders')}>
          {(holders?.top || []).slice(0, 6).map((h: any) => <KV key={h.name} k={h.name} v={h.pct ? (h.pct * 100).toFixed(2) + '%' : big(h.shares)} />)}
          {holders && !holders.top?.length && (holders.holderCount
            ? holders.holderCount.slice(0, 5).map((h: any) => <KV key={h.date} k={`${t('Holder count')} ${h.date}`} v={fmt(h.n, 0)} hint={pct(h.chgPct, 1)} />)
            : <Muted>{t('Not available from current sources.')}</Muted>)}
        </Section>
      </div>
      <Section title={t('Peers across markets')}>
        <div className="flex flex-wrap gap-2 mt-2">
          {peers?.peers.map((q) => (
            <button key={q.id} onClick={() => set({ companyId: q.id })}
              className="border border-edge bg-transparent text-ink rounded-full px-3.5 py-1.5 font-mono text-[0.8125rem] cursor-pointer hover:border-amber">
              {q.ticker} · {lang === 'zh' ? q.nameZh || q.name : q.name || q.nameZh}
            </button>
          ))}
          {peers && !peers.peers.length && <Muted>{t('Not available from current sources.')}</Muted>}
        </div>
      </Section>
    </>
  );
}

// ---------- FINANCIAL ----------
function Financial({ fin }: { fin?: Fin }) {
  const { t, bi } = useT();
  if (!fin) return <Muted>{t('Loading…')}</Muted>;
  if (!fin.annual.length) return <Muted>{t('Not available from current sources.')}</Muted>;
  const cols = [...fin.annual].reverse();
  const ccy = fin.annual[0].currency || '';
  const rows: [string, (r: any) => string][] = [
    [t('Revenue'), (r) => (r.revenue != null ? fmt(r.revenue / 1e9, 1) : '—')],
    [t('Growth YoY'), (r) => pct(r.revenueYoy, 1)],
    [t('Gross margin'), (r) => pctPlain(r.grossMargin)],
    [t('Net margin'), (r) => pctPlain(r.netMargin)],
    [t('Net income'), (r) => (r.netIncome != null ? fmt(r.netIncome / 1e9, 1) : '—')],
    [t('Operating cash flow'), (r) => (r.ocf != null ? fmt(r.ocf / 1e9, 1) : '—')],
    [t('Free cash flow'), (r) => (r.ocf != null && r.capex != null ? fmt((r.ocf - r.capex) / 1e9, 1) : '—')],
  ];
  const latest = fin.annual[0];
  const badge = (s: string) => <span className={`inline-block w-[4.2em] text-center font-mono text-[0.6875rem] uppercase border rounded-[2px] py-[1px] ${s === 'pass' ? 'border-edge text-dim' : 'border-amber text-amber'}`}>{t(s)}</span>;
  return (
    <>
      {fin.read?.fin && bi(fin.read.fin) && <Note label={t('AI read')}><p className="m-0">{bi(fin.read.fin)}</p></Note>}
      <Section title={t('Income and cash flow')} right={`${ccy} bn`}>
        <table className="w-full text-[0.9375rem] border-collapse">
          <thead><tr><th />{cols.map((r) => <th key={r.year} className="text-right font-mono font-normal text-[0.75rem] text-dim py-2">FY{r.year}</th>)}</tr></thead>
          <tbody>{rows.map(([k, f]) => <tr key={k} className="border-t border-line"><td className="py-2">{k}</td>{cols.map((r) => <td key={r.year} className="text-right font-mono">{f(r)}</td>)}</tr>)}</tbody>
        </table>
      </Section>
      <StatGrid items={[
        { k: t('Total assets'), v: latest.totalAssets != null ? fmt(latest.totalAssets / 1e9, 1) : '—', hint: `${ccy} bn` },
        { k: t('Shareholder equity'), v: latest.equity != null ? fmt(latest.equity / 1e9, 1) : '—', hint: `${ccy} bn` },
        { k: t('Debt to assets'), v: pctPlain(latest.debtRatio), hint: `FY${latest.year}` },
        { k: t('FCF ÷ net income'), v: latest.ocf != null && latest.capex != null && latest.netIncome ? `${Math.round(((latest.ocf - latest.capex) / latest.netIncome) * 100)}%` : '—', hint: `FY${latest.year}` },
      ]} />
      {fin.dupont.length > 0 && (
        <Section title={t('DuPont analysis')} right={t('ROE = net margin × asset turnover × equity multiplier')}>
          <table className="w-full text-[0.9375rem] border-collapse">
            <thead><tr><th />{[...fin.dupont].reverse().map((d) => <th key={d.year} className="text-right font-mono font-normal text-[0.75rem] text-dim py-2">FY{d.year}</th>)}</tr></thead>
            <tbody>
              {([[t('Net margin'), (d: any) => d.netMargin.toFixed(1) + '%'], ['× ' + t('Asset turnover'), (d: any) => d.assetTurnover.toFixed(2) + 'x'],
                ['× ' + t('Equity multiplier'), (d: any) => d.equityMultiplier.toFixed(2) + 'x'], ['= ROE', (d: any) => d.roe.toFixed(1) + '%']] as [string, (d: any) => string][]).map(([k, f]) => (
                <tr key={k} className="border-t border-line"><td className="py-2">{k}</td>{[...fin.dupont].reverse().map((d) => <td key={d.year} className={`text-right font-mono ${k === '= ROE' ? 'text-amber' : ''}`}>{f(d)}</td>)}</tr>
              ))}
            </tbody>
          </table>
          {fin.read?.dupont && bi(fin.read.dupont) && <div className="text-[0.9375rem] mt-3"><span className="font-mono text-[0.75rem] text-sky mr-2">{t('AI READ')}</span>{bi(fin.read.dupont)}</div>}
        </Section>
      )}
      {fin.checks.length > 0 && (
        <Section title={t('Quality checks')}>
          {fin.checks.map((c) => (
            <div key={c.k} className="grid grid-cols-[5em_13em_minmax(0,1fr)] gap-3 items-center py-2.5 border-b border-line text-[0.9375rem]">
              {badge(c.status)}<span className="font-medium">{t(c.k)}</span><span className="text-muted">{c.note}</span>
            </div>
          ))}
        </Section>
      )}
      <SourceNote source={fin.source} fetchedAt={fin.fetchedAt} />
    </>
  );
}

// ---------- INSTITUTIONAL VIEWS ----------
function InstViews({ id, q, views, mkt }: { id: string; q: Quote; views?: Views; mkt: Mkt }) {
  const { t, lang } = useT();
  const upDown = useUi((s) => s.upDown);
  const { data: holders } = useCompany<Record<string, any> & Meta>(id, 'holders');
  if (!views) return <Muted>{t('Loading…')}</Muted>;
  const b = Object.fromEntries((views.buckets || []).map((x: any) => [x.k, x.n]));
  const buy = (b['Strong buy'] || 0) + (b['Buy'] || 0), hold = b['Hold'] || 0, sell = (b['Sell'] || 0) + (b['Strong sell'] || 0);
  const n = buy + hold + sell;
  const label = !n ? '—' : buy >= hold && buy >= sell ? t('Buy') : hold >= sell ? t('Hold') : t('Sell');
  const tg = views.target;
  const up = tg?.avg && q.price ? (tg.avg / q.price - 1) * 100 : null;
  const pos = (v: number) => (tg ? Math.max(0, Math.min(100, ((v - tg.lo) / (tg.hi - tg.lo || 1)) * 100)) : 0);
  const ag = views.agent;
  const list = (o: any, k: string): string[] => (o?.[k]?.[lang === 'zh' ? 'zh' : 'en'] || o?.[k]?.en || []);
  return (
    <>
      <div className="grid grid-cols-2 gap-5">
        <Card className="flex flex-col gap-3">
          <div className="flex justify-between text-[0.75rem] tracking-[.06em] uppercase text-dim"><span>{t('Analyst consensus')}</span><span className="font-mono normal-case">{views.n || 0} {t('analysts')}</span></div>
          <div className="text-[1.75rem] text-amber font-medium">{label}</div>
          {n > 0 && (
            <>
              <div className="flex h-2.5 gap-[2px]">
                <div style={{ flex: buy, background: 'var(--amber)' }} /><div style={{ flex: hold, background: 'rgb(var(--faint))' }} /><div style={{ flex: sell, background: 'var(--red)' }} />
              </div>
              <div className="flex gap-4 text-[0.8125rem]"><span>■ <span className="text-amber">{t('Buy')}</span> {buy}</span><span>■ {t('Hold')} {hold}</span><span style={{ color: 'var(--red)' }}>■ {t('Sell')} {sell}</span></div>
            </>
          )}
        </Card>
        <Card className="flex flex-col gap-3">
          <div className="flex justify-between text-[0.75rem] tracking-[.06em] uppercase text-dim"><span>{t('12-month price target')}</span>{up != null && <span className="font-mono normal-case" style={{ color: dirColor(Math.sign(up), mkt, upDown) }}>{pct(up, 1)} {t('vs price')}</span>}</div>
          {tg ? (
            <>
              <div className="font-mono text-[1.75rem]">{q.ccy}{fmt(tg.avg)}</div>
              <div className="relative h-4 mt-1">
                <div className="absolute top-1/2 left-0 right-0 h-px bg-edge" />
                {q.price != null && <div className="absolute top-1/2 w-2.5 h-2.5 -mt-[5px] -ml-[5px] rounded-full bg-ink" style={{ left: `${pos(q.price)}%` }} />}
                <div className="absolute top-0 h-4 w-[2px] bg-amber" style={{ left: `${pos(tg.avg)}%` }} />
              </div>
              <div className="flex justify-between font-mono text-[0.75rem] text-dim"><span>{fmt(tg.lo)}</span><span>● {t('now')} <span className="text-amber">| {t('avg')}</span></span><span>{fmt(tg.hi)}</span></div>
            </>
          ) : <Muted>{t('Not available from current sources.')}</Muted>}
        </Card>
      </div>
      {ag?.view && <Note label={t('Agent view')}><p className="m-0">{lang === 'zh' ? ag.view.zh || ag.view.en : ag.view.en}</p></Note>}
      {ag && (list(ag, 'bull').length > 0 || list(ag, 'bear').length > 0) && (
        <div className="grid grid-cols-2 gap-5">
          <Card><div className="text-[0.8125rem] font-semibold tracking-[.08em] uppercase mb-2" style={{ color: dirColor(1, mkt, upDown) }}>{t('Bull case')}</div>
            {list(ag, 'bull').map((x, i) => <div key={i} className="flex gap-2.5 py-1 text-[0.9375rem]"><span className="text-faint">+</span>{x}</div>)}</Card>
          <Card><div className="text-[0.8125rem] font-semibold tracking-[.08em] uppercase mb-2" style={{ color: dirColor(-1, mkt, upDown) }}>{t('Bear case')}</div>
            {list(ag, 'bear').map((x, i) => <div key={i} className="flex gap-2.5 py-1 text-[0.9375rem]"><span className="text-faint">−</span>{x}</div>)}</Card>
        </div>
      )}
      {views.changes?.length > 0 && (
        <Section title={t('Recent rating changes')}>
          {views.changes.map((c: any, i: number) => (
            <div key={i} className="grid grid-cols-[7em_12em_minmax(0,1fr)_auto] gap-3 items-baseline py-2.5 border-b border-line text-[0.9375rem]">
              <span className="font-mono text-[0.75rem] text-dim">{c.date}</span><span className="font-medium">{c.firm}</span>
              <span className={/down|cut|sell|减持|卖出/i.test(`${c.action} ${c.to}`) ? 'text-[color:var(--red)]' : /up|raise|init|买入|增持/i.test(`${c.action}`) ? 'text-amber' : 'text-muted'}>
                {c.from && c.to ? (c.from === c.to ? `${t('Reiterate')} ${c.to}` : `${c.from} → ${c.to}`) : c.action}{c.title ? ` · ${c.title}` : ''}
              </span>
              {c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="font-mono text-[0.75rem]">PDF</a> : <span />}
            </div>
          ))}
        </Section>
      )}
      <div className="grid grid-cols-2 gap-8">
        <Section title={t('Institutional ownership')}>
          {holders?.overview ? (
            <div className="py-2"><span className="font-mono text-[2rem]">{pctPlain((holders.overview.institutionsPct || 0) * 100)}</span>
              <div className="text-[0.8125rem] text-faint">{t('Insiders')} {pctPlain((holders.overview.insidersPct || 0) * 100)} · {holders.overview.institutionsCount} {t('institutions')}</div></div>
          ) : holders?.holderCount ? (
            <div className="py-2"><span className="font-mono text-[2rem]">{fmt(holders.holderCount[0].n, 0)}</span>
              <div className="text-[0.8125rem] text-faint">{t('Holder count')} · {holders.holderCount[0].date} · {pct(holders.holderCount[0].chgPct, 1)}</div></div>
          ) : <Muted>{t('Not available from current sources.')}</Muted>}
        </Section>
        <Section title={t('Top holders')}>
          {(holders?.top || []).slice(0, 6).map((h: any) => <KV key={h.name} k={h.name} v={h.pct ? (h.pct * 100).toFixed(2) + '%' : big(h.shares)} />)}
          {holders && !holders.top?.length && <Muted>{t('Not available from current sources.')}</Muted>}
        </Section>
      </div>
      <SourceNote source={views.source} fetchedAt={views.fetchedAt} />
    </>
  );
}

export function Company() {
  const { t, lang } = useT();
  const { companyId, market, set } = useUi();
  const { data: lists } = useLists();
  const first = (lists?.co || []).find((x) => market === 'ALL' || x.startsWith(market + ':')) || null;
  const id = companyId || first;
  const { data: q0 } = useQuote(id);
  const live = useLive((s) => (id ? s.quotes[id] : undefined));
  const q = (live ? { ...q0, ...live } : q0) as Quote | undefined;
  const mkt = (id?.split(':')[0] || 'US') as Mkt;
  const [tab, setTab] = useState<Tab>('journey');
  const { data: prof } = useCompany<Prof>(id, 'profile');
  const { data: fin } = useCompany<Fin>(id, 'financials');
  const { data: views } = useCompany<Views>(id, 'views');
  const p = prof?.profile || {};
  const fy = fin?.annual?.[0];
  const range52 = q?.lo52 && q?.hi52 && q.price ? Math.round(((q.price - q.lo52) / (q.hi52 - q.lo52 || 1)) * 100) : null;
  const de = fy?.debtRatio != null && fy.debtRatio < 100 ? fy.debtRatio / (100 - fy.debtRatio) : null;
  const dy = views?.valuation?.dividendYield;
  return (
    <ResearchLayout sidebar={<CompanySidebar id={id} onSelect={(x) => set({ companyId: x })} />}>
      {!id && <Muted>{t('Search a company')} — {t('Your list is empty. Use + ADD to pick items.')}</Muted>}
      {id && !q && <Muted>{t('Loading…')}</Muted>}
      {id && q && (
        <>
          <PageHeader meta={[q.ticker, p.exchange, p.industry || p.sector].filter(Boolean).join(' · ')}
            title={lang === 'zh' ? q.nameZh || q.name : q.name || q.nameZh} sub={lang === 'zh' ? q.name : q.nameZh}
            price={`${q.ccy}${fmt(q.price, priceDigits(q.price))}`} chg={q.pct} mkt={mkt} chgNote={t('today')} />
          <StatGrid cols={5} items={[
            { k: t('Market cap'), v: big(q.mcap, q.ccy), hint: t('Local currency') },
            { k: 'P/E', v: q.peTtm ? fmt(q.peTtm, 1) : '—', hint: t('Price ÷ earnings') },
            { k: t('Dividend yield'), v: dy != null ? `${(dy * (dy < 1 ? 100 : 1)).toFixed(2)}%` : '—', hint: t('Cash paid per year') },
            { k: t('52-week range'), v: q.lo52 && q.hi52 ? `${fmt(q.lo52, 0)}–${fmt(q.hi52, 0)}` : '—', hint: range52 != null ? `${range52}% ${t('of range')}` : undefined },
            { k: t('Revenue'), v: fy?.revenue != null ? fmt(fy.revenue / 1e9, 1) : '—', hint: fy ? `${fy.currency} bn · FY${fy.year}` : undefined },
            { k: t('Net profit'), v: fy?.netIncome != null ? fmt(fy.netIncome / 1e9, 1) : '—', hint: fy ? `${fy.currency} bn · FY${fy.year}` : undefined },
            { k: t('Gross margin'), v: pctPlain(fy?.grossMargin), hint: fy ? `FY${fy.year}` : undefined },
            { k: t('Net margin'), v: pctPlain(fy?.netMargin), hint: t('Net profit ÷ revenue') },
            { k: t('Debt-to-equity'), v: de != null ? `${de.toFixed(2)}x` : '—', hint: t('Total liabilities ÷ equity') },
            { k: 'ROE', v: pctPlain(fy?.roe), hint: t('Net profit ÷ equity') },
            ...(p.staff ? [{ k: t('Employees'), v: fmt(+p.staff, 0), hint: t('Full-time') }] : []),
          ]} />
          <UTabs items={[{ id: 'journey', label: t('Journey') }, { id: 'updates', label: t('Updates') }, { id: 'overview', label: t('Overview') },
            { id: 'financial', label: t('Financial') }, { id: 'views', label: t('Institutional views') }]} value={tab} onChange={setTab} />
          {tab === 'journey' && <Journey id={id} mkt={mkt} prof={prof} />}
          {tab === 'updates' && <Updates id={id} mkt={mkt} />}
          {tab === 'overview' && <Overview id={id} prof={prof} views={views} />}
          {tab === 'financial' && <Financial fin={fin} />}
          {tab === 'views' && <InstViews id={id} q={q} views={views} mkt={mkt} />}
        </>
      )}
    </ResearchLayout>
  );
}
