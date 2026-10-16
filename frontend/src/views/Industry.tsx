// Industries page — prototype layout: industry × market list with 1M return; header + 4 stats; tabs
// UPDATES (weekly AI summary + latest developments), OVERVIEW (view, market size, bull/bear),
// VALUE CHAIN MAP (3 tiers), COMPETITIVE LANDSCAPE (market share + peer table), TRACKING METRICS.
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/data/api';
import { useIndustry, useLists, usePutList } from '@/data/queries';
import { useLive } from '@/data/live';
import { useUi } from '@/data/ui';
import { useT } from '@/i18n';
import { big, dayShort, dirColor, fmt, pct } from '@/lib/format';
import { eventTitle } from '@/components/AIRead';
import { Card, Muted, Note, PageHeader, ResearchLayout, Section, SideRow, SmallBtn, StatGrid, UTabs } from '@/components/page';
import type { Bi, Mkt, WireEvent } from '@/lib/types';

type Pair = { k_en: string; k_zh: string; v_en: string; v_zh: string };
interface Pack {
  stance_en: string; stance_zh: string; view_en: string; view_zh: string; week_head_en: string; week_head_zh: string;
  view_points?: Bi[]; week_points?: Bi[]; drivers: Pair[]; risks: Pair[];
  size: { title_en: string; title_zh: string; unit: string; series: { year: string; value: number; estimate: boolean }[]; cagr: string; url: string } | null;
  chain: { tier_en: string; tier_zh: string; segments: { name_en: string; name_zh: string; products_en: string; products_zh: string; companies: { id: string; name: string; tags_en?: string[]; tags_zh?: string[] }[] }[] }[];
  share: { title_en: string; title_zh: string; items: { k: string; v: number }[]; note_en?: string; note_zh?: string; url: string } | null;
  metrics: { name_en: string; name_zh: string; value: string; chg: string; note_en?: string; note_zh?: string; url: string }[];
  plans: { who: string; what_en: string; what_zh: string; cap: string; when: string; url: string }[];
  sources: { title: string; url: string; date?: string }[]; model: string; generatedAt: number;
}
interface PeerRow { id: string; ticker: string; name: string; nameZh: string; mkt: Mkt; ccy: string; price: number; pct: number; mcap: number | null; pe: number | null; fwdPe: number | null; revGrowth: number | null; grossMargin: number | null; m1: number | null }
interface Ind {
  id: string; code: string; name: string; nameZh: string; mkt: string; developments: WireEvent[]; pack: Pack | null;
  packState: string; packError: string | null; peers: PeerRow[];
  stats: { ret1m: number | null; ret1mBasis: string | null; news7d: number; news7dPrev: number; size: { value: number | null; year: string; estimate: boolean; unit: string; cagr: string } | null; medianPe: number | null; peBasis: string };
}
interface CatRow { id: string; ind: string; mkt: Mkt; code: string; name: string; nameZh: string; events7d: number; ret1m: number | null }
type Tab = 'updates' | 'overview' | 'chain' | 'landscape' | 'metrics';

function IndustrySidebar({ sel, onSelect }: { sel: string | null; onSelect: (id: string) => void }) {
  const { t, lang } = useT();
  const market = useUi((s) => s.market);
  const { data: cat } = useQuery({ queryKey: ['industries', market], queryFn: () => api.get<CatRow[]>(`/industries?market=${market}`), refetchInterval: 300_000 });
  const { data: lists } = useLists();
  const put = usePutList();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const mine = lists?.ind || [];
  const rows = (cat || []).filter((r) => !mine.length || mine.includes(r.id));
  const rest = (cat || []).filter((r) => mine.length && !mine.includes(r.id));
  const save = (items: string[]) => put.mutate({ name: 'ind', items });
  return (
    <div>
      <div className="flex items-center justify-between px-3.5 h-[44px] border-b border-line">
        <span className="font-mono text-[0.75rem] tracking-[.08em] uppercase text-faint">{t('My industries')} {rows.length}</span>
        <div className="flex gap-1">
          {mine.length > 0 && <SmallBtn active={adding} onClick={() => setAdding(!adding)}>{t('+ ADD')}</SmallBtn>}
          <SmallBtn active={editing} onClick={() => setEditing(!editing)}>{editing ? t('Done') : t('EDIT')}</SmallBtn>
        </div>
      </div>
      {adding && rest.map((r) => (
        <button key={r.id} onClick={() => save([...mine, r.id])} className="flex w-full justify-between border-0 border-b border-line bg-chip px-3.5 py-2 text-[0.875rem] text-ink cursor-pointer">
          <span>{lang === 'zh' ? r.nameZh : r.name}</span><span className="font-mono text-faint">{r.code} +</span>
        </button>
      ))}
      {rows.map((r) => (
        <SideRow key={r.id} name={lang === 'zh' ? r.nameZh : r.name} sub={`${r.code} · ${t(r.mkt)}`} chg={r.ret1m} mkt={r.mkt}
          selected={r.id === sel} editing={editing} onClick={() => onSelect(r.id)}
          onRemove={() => save((mine.length ? mine : (cat || []).map((c) => c.id)).filter((x) => x !== r.id))} />
      ))}
    </div>
  );
}

export function Industry() {
  const { t, bi, lang } = useT();
  const { industryId, market, set } = useUi();
  const upDown = useUi((s) => s.upDown);
  const coList = useLists().data?.co || [];
  const bump = useLive((s) => s.reportVersion);
  const defMkt = market === 'ALL' ? 'US' : market;
  const sel = industryId?.includes(':') ? (market === 'ALL' || industryId.endsWith(':' + market) ? industryId : `${industryId.split(':')[0]}:${defMkt}`)
    : `${industryId || 'semi'}:${defMkt}`;
  const [ind, mkt] = sel.split(':') as [string, Mkt];
  const { data, isLoading } = useIndustry<Ind>(ind, mkt);
  const [tab, setTab] = useState<Tab>('updates');
  const [metric, setMetric] = useState(0);
  useEffect(() => setMetric(0), [sel, bump]);
  const p = data?.pack;
  const b = (o: any, k: string) => bi({ en: o?.[`${k}_en`] || '', zh: o?.[`${k}_zh`] || '' });
  const openCo = (cid: string) => set({ view: 'company', companyId: cid });
  const st = data?.stats;
  const packMsg = !data ? null : data.packState === 'disabled' ? t('AI reads are off: add GLM_API_KEY to .env')
    : data.packState === 'failed' ? `${t('Industry research pack')}: ${data.packError}` : t('Researching this industry with cited web search… (about a minute)');
  const tierColors = ['var(--amber)', 'var(--sky)', 'rgb(var(--muted))'];
  return (
    <ResearchLayout sidebar={<IndustrySidebar sel={sel} onSelect={(x) => set({ industryId: x })} />}>
      {isLoading && <Muted>{t('Loading…')}</Muted>}
      {data && (
        <>
          <PageHeader meta={[data.code, t(mkt), p ? b(p, 'stance') : null].filter(Boolean).join(' · ')} title={lang === 'zh' ? data.nameZh : data.name} sub={t(mkt === 'CN' ? 'China A' : mkt === 'HK' ? 'Hong Kong' : 'US')} />
          <StatGrid items={[
            { k: t('1M return'), v: pct(st?.ret1m), color: dirColor(Math.sign(st?.ret1m || 0), mkt, upDown), hint: st?.ret1mBasis || t('Not available from current sources.') },
            { k: t('News flow (7D)'), v: String(st?.news7d ?? 0), hint: `${(st?.news7d || 0) - (st?.news7dPrev || 0) >= 0 ? '+' : ''}${(st?.news7d || 0) - (st?.news7dPrev || 0)} ${t('vs prior week')}` },
            { k: `${t('Market size')} ${st?.size?.year || ''}${st?.size?.estimate ? 'E' : ''}`, v: st?.size?.value != null ? fmt(st.size.value, st.size.value < 100 ? 1 : 0) : '—', hint: st?.size ? `${st.size.unit}${st.size.cagr ? ' · CAGR ' + st.size.cagr : ''}` : undefined },
            { k: t('Median P/E'), v: st?.medianPe != null ? `${st.medianPe.toFixed(0)}x` : '—', hint: st?.peBasis },
          ]} />
          <UTabs items={[{ id: 'updates', label: t('Updates') }, { id: 'overview', label: t('Overview') }, { id: 'chain', label: t('Value chain map') },
            { id: 'landscape', label: t('Competitive landscape') }, { id: 'metrics', label: t('Tracking metrics') }]} value={tab} onChange={setTab} />

          {tab === 'updates' && (
            <>
              {p ? (
                <div className="border border-amber rounded-[2px] p-5" style={{ background: 'color-mix(in oklch, var(--amber) 6%, transparent)' }}>
                  <div className="flex justify-between font-mono text-[0.75rem] tracking-[.08em] uppercase"><span className="text-amber">{t('Weekly summary · AI')}</span><span className="text-dim normal-case">{dayShort(new Date(p.generatedAt - 6 * 86400_000).toISOString().slice(0, 10), lang)} – {dayShort(new Date(p.generatedAt).toISOString().slice(0, 10), lang)}</span></div>
                  <div className="text-[1.25rem] font-medium mt-2 leading-[1.35]">{b(p, 'week_head')}</div>
                  <div className="flex flex-col gap-2 mt-3">{(p.week_points || []).map((w, i) => <div key={i} className="flex gap-3 text-[0.9375rem]"><span className="text-amber">›</span>{bi(w)}</div>)}</div>
                </div>
              ) : <Muted>{packMsg}</Muted>}
              <Section title={t('Latest developments')}>
                {data.developments.map((e) => (
                  <div key={e.id} className="grid grid-cols-[7.5em_minmax(0,1fr)] gap-4 py-3.5 border-b border-line">
                    <div className="font-mono text-[0.75rem] text-dim">{dayShort(new Date(e.ts).toISOString().slice(0, 10), lang)}<br />{e.mkts.map((m) => t(m)).join(' · ')}</div>
                    <div>
                      <a href={e.url || undefined} target="_blank" rel="noreferrer" className="text-[1rem] font-medium text-ink no-underline hover:underline">{eventTitle(e, bi)}</a>
                      {e.ai?.sentiment && <span className="font-mono text-[0.75rem] ml-2" style={{ color: dirColor(e.ai.sentiment === 'bullish' ? 1 : e.ai.sentiment === 'bearish' ? -1 : 0, mkt, upDown) }}>{e.ai.sentiment === 'bullish' ? '▲ positive' : e.ai.sentiment === 'bearish' ? '▼ negative' : '– mixed'}</span>}
                      {e.ai?.comment && <div className="text-[0.9375rem] text-muted mt-1"><span className="font-mono text-[0.6875rem] text-sky mr-2">{t('AI READ')}</span>{bi(e.ai.comment)}</div>}
                    </div>
                  </div>
                ))}
                {!data.developments.length && <Muted>{t('No updates for this market.')}</Muted>}
              </Section>
            </>
          )}

          {tab === 'overview' && (p ? (
            <>
              <Note label={t('AI insights')}>
                <p className="m-0">{b(p, 'view')}</p>
                {(p.view_points || []).map((v, i) => <div key={i} className="flex gap-3 text-[0.9375rem]"><span className="text-faint">›</span>{bi(v)}</div>)}
              </Note>
              {p.size && (
                <Card className="flex flex-col gap-3">
                  <div className="flex justify-between"><span className="text-[0.8125rem] font-semibold tracking-[.08em] uppercase text-muted">{t('Market size')}</span><span className="font-mono text-[0.75rem] text-dim">{b(p.size, 'title')} · {p.size.unit}</span></div>
                  <div className="flex items-end gap-3 h-[160px]">
                    {p.size.series.map((s) => {
                      const mx = Math.max(...p.size!.series.map((x) => x.value || 0)) || 1;
                      return (
                        <div key={s.year} className="flex flex-col items-center gap-1 flex-1 justify-end h-full">
                          <span className="font-mono text-[0.75rem]">{fmt(s.value, s.value < 100 ? 1 : 0)}</span>
                          <div className="w-full" style={{ height: `${(s.value / mx) * 120}px`, background: s.estimate ? 'color-mix(in oklch, var(--amber) 15%, transparent)' : 'var(--amber)', border: '1px solid var(--amber)' }} />
                          <span className="font-mono text-[0.75rem] text-dim">{s.year}{s.estimate ? 'E' : ''}</span>
                        </div>
                      );
                    })}
                  </div>
                  <span className="text-[0.8125rem] text-faint">E = {t('estimate')} · CAGR {p.size.cagr} · <a href={p.size.url} target="_blank" rel="noreferrer">{t('Source')}</a></span>
                </Card>
              )}
              <div className="grid grid-cols-2 gap-8">
                {[['Bull case', p.drivers, 1], ['Bear case', p.risks, -1]].map(([title, arr, d]) => (
                  <section key={title as string}>
                    <div className="text-[0.8125rem] font-semibold tracking-[.08em] uppercase border-b border-line pb-2" style={{ color: dirColor(d as number, mkt, upDown) }}>{t(title as string)}</div>
                    {(arr as Pair[] || []).map((x, i) => (
                      <div key={i} className="grid grid-cols-[2.2em_minmax(0,1fr)] py-3 border-b border-line">
                        <span className="font-mono text-[0.8125rem] text-faint">{String(i + 1).padStart(2, '0')}</span>
                        <span><span className="text-[1rem] font-medium">{b(x, 'k')}</span><br /><span className="text-[0.9375rem] text-muted">{b(x, 'v')}</span></span>
                      </div>
                    ))}
                  </section>
                ))}
              </div>
            </>
          ) : <Muted>{packMsg}</Muted>)}

          {tab === 'chain' && (p?.chain?.length ? (
            <>
              <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${Math.min(3, p.chain.length)}, minmax(0,1fr))` }}>
                {p.chain.slice(0, 3).map((tier, i) => (
                  <div key={i} className="flex flex-col gap-3">
                    <div className="border-t-2 pt-2" style={{ borderColor: tierColors[i] }}>
                      <span className="font-mono text-[0.75rem] tracking-[.08em] uppercase" style={{ color: tierColors[i] }}>{b(tier, 'tier')}</span>
                    </div>
                    {tier.segments.map((sg, j) => (
                      <Card key={j} className="flex flex-col gap-2 !p-4">
                        <div className="text-[1rem] font-medium">{b(sg, 'name')}</div>
                        <div className="text-[0.8125rem] text-muted"><span className="font-mono text-[0.6875rem] text-faint mr-1.5">{t('PRODUCTS')}</span>{b(sg, 'products')}</div>
                        {sg.companies.map((c) => {
                          const tags = (lang === 'zh' ? c.tags_zh : c.tags_en) || c.tags_en || [];
                          return (
                            <button key={c.id} onClick={() => openCo(c.id)}
                              className={`text-left border rounded-[2px] bg-transparent px-2.5 py-1.5 cursor-pointer text-ink ${coList.includes(c.id) ? 'border-amber' : 'border-edge hover:border-amber'}`}>
                              <span className="text-[0.9375rem]">{c.name}</span> <span className="font-mono text-[0.75rem] text-faint">{c.id.split(':')[1]}</span>
                              {tags.length > 0 && <div className="flex flex-wrap gap-1 mt-1">{tags.map((tg) => <span key={tg} className="bg-chip text-[0.75rem] text-muted px-1.5 rounded-[2px]">{tg}</span>)}</div>}
                            </button>
                          );
                        })}
                      </Card>
                    ))}
                  </div>
                ))}
              </div>
              <div className="text-[0.8125rem] text-faint">{t('Amber-bordered companies are on your company list. Click any company to open its page.')}</div>
            </>
          ) : <Muted>{p ? t('Not available from current sources.') : packMsg}</Muted>)}

          {tab === 'landscape' && (
            <>
              {p?.share && (
                <Section title={`${t('Market share')} · ${b(p.share, 'title')}`}>
                  {p.share.items.map((s, i) => (
                    <div key={s.k} className="grid grid-cols-[14em_minmax(0,1fr)_4em] gap-4 items-center py-2.5 border-b border-line text-[0.9375rem]">
                      <span>{s.k}</span><div className="h-2 bg-line"><div className="h-2" style={{ width: `${Math.min(100, s.v)}%`, background: i === 0 ? 'var(--amber)' : 'color-mix(in oklch, var(--amber) 55%, transparent)' }} /></div><span className="font-mono text-right">{s.v}%</span>
                    </div>
                  ))}
                  {b(p.share, 'note') && <Note label={t('AI read')}><p className="m-0 text-[0.9375rem]">{b(p.share, 'note')} <a href={p.share.url} target="_blank" rel="noreferrer" className="text-[0.8125rem]">{t('Source')}</a></p></Note>}
                </Section>
              )}
              <Section title={t('Peer comparison')}>
                {data.peers.length ? (
                  <div className="border border-line rounded-[2px] overflow-hidden mt-2">
                    <div className="grid grid-cols-[6em_minmax(0,1fr)_3.5em_7em_6.5em_6.5em_5em_5.5em] gap-2 px-4 py-2.5 bg-panel text-[0.75rem] tracking-[.06em] uppercase text-dim">
                      <span>{t('Ticker')}</span><span>{t('Company')}</span><span>{t('Mkt')}</span><span className="text-right">{t('Market cap')}</span><span className="text-right">{t('Rev growth')}</span><span className="text-right">{t('Gross margin')}</span><span className="text-right">P/E</span><span className="text-right">1M</span>
                    </div>
                    {data.peers.map((r) => (
                      <button key={r.id} onClick={() => openCo(r.id)} className="grid grid-cols-[6em_minmax(0,1fr)_3.5em_7em_6.5em_6.5em_5em_5.5em] gap-2 w-full text-left border-0 border-t border-line bg-transparent px-4 py-2.5 text-[0.9375rem] text-ink cursor-pointer hover:bg-hover">
                        <span className="font-mono">{r.ticker}</span><span className="truncate">{lang === 'zh' ? r.nameZh || r.name : r.name || r.nameZh}</span>
                        <span className="font-mono text-[0.75rem] text-faint">{t(r.mkt)}</span><span className="font-mono text-right">{big(r.mcap, r.ccy)}</span>
                        <span className="font-mono text-right">{pct(r.revGrowth, 0)}</span><span className="font-mono text-right">{r.grossMargin != null ? r.grossMargin.toFixed(0) + '%' : '—'}</span>
                        <span className="font-mono text-right">{(r.fwdPe || r.pe) ? `${(r.fwdPe || r.pe)!.toFixed(0)}x` : '—'}</span>
                        <span className="font-mono text-right" style={{ color: dirColor(Math.sign(r.m1 || 0), r.mkt, upDown) }}>{pct(r.m1)}</span>
                      </button>
                    ))}
                  </div>
                ) : <Muted>{p ? t('Not available from current sources.') : packMsg}</Muted>}
                <div className="text-[0.75rem] text-faint mt-2">{t('P/E is forward where the source has it, otherwise trailing. Growth and margin from Yahoo key statistics (US/HK).')}</div>
              </Section>
            </>
          )}

          {tab === 'metrics' && (p ? (
            <>
              {p.metrics?.length ? (
                <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-5 items-start">
                  <div className="flex flex-col gap-2">
                    {p.metrics.map((m, i) => (
                      <button key={i} onClick={() => setMetric(i)} className={`text-left border rounded-[2px] bg-panel px-4 py-3 cursor-pointer text-ink ${metric === i ? 'border-amber' : 'border-line hover:border-edge'}`}>
                        <div className="text-[0.9375rem]">{b(m, 'name')}</div>
                        <div className="font-mono text-[1.125rem] mt-0.5">{m.value} <span className="text-[0.8125rem] text-dim">{m.chg}</span></div>
                      </button>
                    ))}
                  </div>
                  {p.metrics[metric] && (
                    <Card className="flex flex-col gap-3">
                      <span className="text-[0.75rem] font-semibold tracking-[.08em] uppercase text-sky">{t('Latest reading')}</span>
                      <div className="text-[1.125rem] font-medium">{b(p.metrics[metric], 'name')}</div>
                      <div className="font-mono text-[1.75rem]">{p.metrics[metric].value} <span className="text-[0.9375rem] text-dim">{p.metrics[metric].chg}</span></div>
                      {b(p.metrics[metric], 'note') && <p className="m-0 text-[0.9375rem] text-muted border-t border-line pt-3">{b(p.metrics[metric], 'note')}</p>}
                      <a href={p.metrics[metric].url} target="_blank" rel="noreferrer" className="text-[0.8125rem]">{t('Source')}</a>
                      <span className="text-[0.75rem] text-faint">{t('A 12-month trend needs a time series no reachable source provides; the latest cited reading is shown.')}</span>
                    </Card>
                  )}
                </div>
              ) : <Muted>{t('Not available from current sources.')}</Muted>}
              {p.plans?.length > 0 && (
                <Section title={t('Capacity expansion plans')}>
                  {p.plans.map((pl, i) => (
                    <a key={i} href={pl.url} target="_blank" rel="noreferrer" className="grid grid-cols-[11em_minmax(0,1fr)_7em_8em] gap-4 py-3 border-b border-line text-[0.9375rem] text-ink no-underline hover:bg-hover">
                      <span className="font-medium">{pl.who}</span><span className="text-muted">{b(pl, 'what')}</span><span className="font-mono text-right">{pl.cap || '—'}</span><span className="font-mono text-right text-dim">{pl.when}</span>
                    </a>
                  ))}
                </Section>
              )}
              <details className="text-[0.8125rem] text-faint"><summary className="cursor-pointer">{t('Sources')} ({p.sources.length}) · {p.model}</summary>
                {p.sources.map((s) => <div key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> {s.date}</div>)}
              </details>
            </>
          ) : <Muted>{packMsg}</Muted>)}
        </>
      )}
    </ResearchLayout>
  );
}
