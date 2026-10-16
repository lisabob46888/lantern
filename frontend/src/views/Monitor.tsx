import { useEffect, useMemo, useState } from 'react';
import { useArchiveDays, useCalendar, useLists, useNtk, useWire } from '@/data/queries';
import { useLive } from '@/data/live';
import { useUi } from '@/data/ui';
import { useT } from '@/i18n';
import { countdown, dayShort, hm } from '@/lib/format';
import { AIRead, eventTitle } from '@/components/AIRead';
import { Empty, ImpactTag, Loading, MktTag, Panel, Tabs } from '@/components/ui';
import type { WireEvent } from '@/lib/types';

const NEW_MS = 5 * 60_000;

function WireRow({ e, active, onPick }: { e: WireEvent; active: boolean; onPick: () => void }) {
  const { t, bi } = useT();
  const fresh = Date.now() - e.receivedAt < NEW_MS;
  return (
    <button onClick={onPick}
      className={`grid grid-cols-[62px_minmax(0,1fr)] gap-2.5 w-full text-left border-0 border-b border-line2 px-3 py-2.5 cursor-pointer text-ink hover:bg-hover ${active ? 'bg-chip' : 'bg-transparent'}`}>
      <span className="font-mono text-[0.8125rem] text-dim pt-[1px]">{hm(e.ts)}</span>
      <div className="flex flex-col gap-1 min-w-0">
        <div className="flex flex-wrap gap-1.5 items-center font-mono text-[0.75rem]">
          {e.mkts.map((m) => <MktTag key={m} mkt={m} />)}
          <ImpactTag impact={e.impact} />
          {e.kind === 'filing' && <span className="text-sky">FILING</span>}
          {e.state === 'pending' && <span className="text-faint">{t('AI read pending')}</span>}
          {fresh && <span className="text-amber">{t('NEW')}</span>}
          <span className="text-faint ml-auto">{e.source}</span>
        </div>
        <div className="text-[0.9375rem] leading-[1.4]">{eventTitle(e, bi)}</div>
        {e.ai?.comment && bi(e.ai.comment) && <div className="text-[0.875rem] leading-[1.45] text-muted">{bi(e.ai.comment)}</div>}
      </div>
    </button>
  );
}

export function Monitor() {
  const { t, bi, lang } = useT();
  const { market, day, storyId, wireMode, set } = useUi();
  const { data: days } = useArchiveDays();
  const { data: snap, isLoading } = useWire(market, day);
  const seedWire = useLive((s) => s.seedWire);
  const liveWire = useLive((s) => s.wire);
  const hidden = useLive((s) => s.hidden);
  const { data: lists } = useLists();
  const { data: ntk } = useNtk(market, day);
  const { data: cal } = useCalendar(market);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const h = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(h); }, []);
  useEffect(() => { if (!day && snap) seedWire(snap.items); }, [snap, day, seedWire]);

  const items = useMemo(() => {
    const base = day ? snap?.items || [] : liveWire;
    let rows = base.filter((e) => !hidden.has(e.id) && e.state !== 'skipped' && (market === 'ALL' || e.mkts.includes(market as never)));
    if (wireMode === 'watch') {
      const watch = new Set([...(lists?.co || []), ...(lists?.ix || [])]);
      const inds = new Set(lists?.ind || []);
      rows = rows.filter((e) => e.symbols.some((s) => watch.has(s)) || e.industries.some((i) => inds.has(i)));
    }
    return rows;
  }, [day, snap, liveWire, hidden, market, wireMode, lists]);

  const pick = (e: WireEvent) => e.storyId && set({ storyId: e.storyId });
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });

  return (
    <div className="flex flex-col gap-px bg-line min-h-full">
      <div className="bg-strip flex flex-wrap items-center gap-x-2.5 gap-y-2 px-4 py-2">
        <span className="font-mono text-[0.75rem] tracking-[.08em] text-dim">{t('DATE')}</span>
        <div className="flex flex-wrap gap-1">
          {[{ date: null as string | null, label: t('Today') }, ...(days || []).filter((d) => d.date !== today).slice(0, 6).map((d) => ({ date: d.date, label: dayShort(d.date, lang) }))].map((c) => (
            <button key={c.date || 'live'} onClick={() => set({ day: c.date })}
              className={`border rounded px-2.5 py-1 text-[0.875rem] cursor-pointer ${day === c.date ? 'bg-ink text-page border-ink' : 'bg-transparent text-ink border-edge'}`}>{c.label}</button>
          ))}
        </div>
        <span className="text-[0.875rem] text-dim">{day ? t('Archive') : t('Live session')}</span>
      </div>

      <div className="flex flex-wrap gap-px">
        <Panel className="flex-[1_1_320px] h-[600px]" title={day ? t('Wire') : t('Live wire')}
          right={<Tabs items={[{ id: 'all', label: t('All') }, { id: 'watch', label: t('WATCHLIST') }]} value={wireMode} onChange={(v) => set({ wireMode: v })} />}>
          {isLoading && !items.length && <Loading />}
          {items.map((e) => <WireRow key={e.id} e={e} active={e.storyId === storyId} onPick={() => pick(e)} />)}
          {!isLoading && !items.length && <Empty>{wireMode === 'watch' ? t('Your list is empty. Use + ADD to pick items.') : t('No wire items for this date and market.')}</Empty>}
        </Panel>

        <Panel className="flex-[1.1_1_340px] h-[600px]" title={t('Need to know')} right={<span>{ntk?.items.length || 0}</span>}>
          {ntk?.items.map((k, i) => (
            <button key={k.storyId} onClick={() => set({ storyId: k.storyId })}
              className={`grid grid-cols-[26px_minmax(0,1fr)] gap-2.5 w-full text-left border-0 border-b border-line2 px-3 py-3 cursor-pointer text-ink hover:bg-hover ${storyId === k.storyId ? 'bg-chip' : 'bg-transparent'}`}>
              <span className="font-mono text-[1.25rem] leading-[1.1] text-amber">{i + 1}</span>
              <div className="flex flex-col gap-[5px] min-w-0">
                <div className="text-[1rem] font-semibold leading-[1.3]">{bi(k.title)}</div>
                <div className="text-[0.9062rem] leading-[1.5] text-muted">{bi(k.why)}</div>
                <div className="font-mono text-[0.75rem] text-faint">{k.mkts.map((m) => t(m)).join(' · ')} · {t('IMPACT')} {k.impact}</div>
              </div>
            </button>
          ))}
          {ntk && !ntk.items.length && <Empty>{ntk.aiEnabled ? t('Nothing recorded for this date.') : t('AI reads are off: add GLM_API_KEY to .env')}</Empty>}
        </Panel>

        <Panel className="flex-[1.5_1_440px] h-[600px]" title={t('AI read')} bodyClass="px-[18px] py-4">
          <AIRead storyId={storyId} />
        </Panel>
      </div>

      <div className="flex flex-wrap gap-px">
        <Panel className="flex-[1_1_300px] min-h-[200px]" title={t('Upcoming countdown')}>
          {(cal || []).map((ev) => (
            <a key={ev.id} href={ev.url || undefined} target="_blank" rel="noreferrer"
              className="grid grid-cols-[34px_minmax(0,1fr)_auto] gap-2.5 items-center px-3.5 py-2 border-b border-line2 text-ink no-underline">
              <span className="font-mono text-[0.75rem] text-muted border border-edge rounded-[3px] text-center">{t(ev.mkt)}</span>
              <span className="text-[0.875rem] leading-[1.35]">{lang === 'zh' && ev.titleZh ? ev.titleZh : ev.title} <span className="text-faint font-mono text-[0.75rem]">· {ev.source}</span></span>
              <span className="font-mono text-[0.8125rem]" style={{ color: ev.at - now < 3600_000 ? 'var(--amber)' : 'rgb(var(--muted))' }}>{countdown(ev.at, now)}</span>
            </a>
          ))}
          {cal && !cal.length && <Empty>{t('No data from any source.')}</Empty>}
        </Panel>
      </div>
    </div>
  );
}
