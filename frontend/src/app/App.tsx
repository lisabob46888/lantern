import { useEffect, useState } from 'react';
import { useIndices, useSessions } from '@/data/queries';
import { useLive } from '@/data/live';
import { TEXT_PX, useUi, type View } from '@/data/ui';
import { useT } from '@/i18n';
import { dirColor, fmt, hm } from '@/lib/format';
import { SearchBox } from '@/components/SearchBox';
import { Monitor } from '@/views/Monitor';
import { Market } from '@/views/Market';
import { Company } from '@/views/Company';
import { Industry } from '@/views/Industry';
import { Settings } from '@/views/Settings';
import type { MktFilter, Quote, Session } from '@/lib/types';

const VIEWS: [View, string][] = [['monitor', 'Monitor'], ['market', 'Index'], ['company', 'Companies'], ['industry', 'Industries'], ['settings', 'Settings']];
const MARKETS: MktFilter[] = ['ALL', 'US', 'CN', 'HK'];
const STATUS_COLOR: Record<string, string> = { OPEN: 'var(--green)', PRE: 'var(--amber)', LUNCH: 'var(--amber)', POST: 'var(--sky)', CLOSED: 'rgb(var(--faint))' };

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const h = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(h);
  }, [ms]);
  return now;
}

/** Session state recomputed every second on the client from the server's schedule. */
function liveStatus(s: Session, now: number): string {
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: s.tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(now);
  const g = (k: string) => f.find((p) => p.type === k)?.value || '';
  const date = `${g('year')}-${g('month')}-${g('day')}`;
  const mins = (+g('hour') % 24) * 60 + +g('minute');
  if (!s.tradingDays.includes(date)) return 'CLOSED';
  if (s.sessions.some(([a, b]) => mins >= a && mins < b)) return 'OPEN';
  if (mins < s.sessions[0][0] && mins >= s.sessions[0][0] - 90) return 'PRE';
  if (s.sessions.length > 1 && mins >= s.sessions[0][1] && mins < s.sessions[1][0]) return 'LUNCH';
  return 'CLOSED';
}

function Header() {
  const { t, lang } = useT();
  const { view, market, theme, set } = useUi();
  const [langOpen, setLangOpen] = useState(false);
  const openSec = (s: Quote) => (s.kind === 'index' ? set({ view: 'market', indexId: s.id }) : set({ view: 'company', companyId: s.id }));
  return (
    <header className="flex-none flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 border-b border-line bg-page">
      <div className="flex items-center gap-2 flex-none">
        <div className="w-[18px] h-[18px] rounded-full bg-ink flex items-center justify-center"><div className="w-[7px] h-[7px] rounded-full bg-amber" /></div>
        <span className="font-mono text-[1rem] font-medium tracking-[.06em] text-amber">LANTERN</span>
      </div>
      <div className="flex bg-chip rounded-[2px] p-[2px] gap-[2px] flex-none">
        {MARKETS.map((m) => (
          <button key={m} onClick={() => set({ market: m })}
            className={`border-0 px-2.5 py-[5px] rounded-[2px] font-mono text-[0.8125rem] tracking-[.04em] uppercase cursor-pointer font-medium whitespace-nowrap ${market === m ? 'bg-ink text-page' : 'bg-transparent text-ink'}`}>
            {t(m === 'ALL' ? 'All' : m)}
          </button>
        ))}
      </div>
      <div className="flex gap-[2px] flex-none">
        {VIEWS.map(([id, label], i) => (
          <button key={id} onClick={() => set({ view: id })}
            className={`flex items-center gap-1.5 border px-2 py-1 pl-1 rounded-[2px] font-mono text-[0.875rem] tracking-[.04em] uppercase cursor-pointer font-medium whitespace-nowrap hover:border-amber ${view === id ? 'bg-amber text-page border-amber' : 'bg-transparent text-amber border-edge'}`}>
            <span className={`text-[0.75rem] px-1 py-[1px] rounded-[1px] ${view === id ? 'bg-page text-amber' : 'bg-line text-muted'}`}>F{i + 1}</span>{t(label)}
          </button>
        ))}
      </div>
      <div className="flex-[1_1_360px] max-w-[560px] min-w-[240px] mx-auto"><SearchBox onPick={openSec} /></div>
      <button onClick={() => set({ theme: theme === 'dark' ? 'light' : 'dark' })} title={t(theme === 'dark' ? 'Light mode' : 'Dark mode')}
        className="flex-none ml-auto border border-edge bg-panel text-ink rounded-[2px] w-9 h-[30px] cursor-pointer hover:border-amber text-[1rem] leading-none">
        {theme === 'dark' ? '☀' : '☾'}
      </button>
      <div className="relative flex-none" translate="no">
        <button onClick={() => setLangOpen(!langOpen)} className="flex items-center gap-1.5 border border-edge bg-panel text-ink rounded-[2px] px-2.5 py-[5px] font-mono text-[0.8125rem] cursor-pointer hover:border-amber">
          {lang === 'zh' ? '中文' : 'EN'} ▾
        </button>
        {langOpen && (
          <>
            <div className="fixed inset-0 z-[70]" onClick={() => setLangOpen(false)} />
            <div className="absolute right-0 top-9 w-[200px] z-[71] bg-panel border border-edge rounded-[2px] shadow-[0_8px_24px_var(--shadow)]">
              <div className="px-2.5 py-1.5 font-mono text-[0.6875rem] tracking-[.08em] text-faint">LANGUAGE · 语言</div>
              {(['en', 'zh'] as const).map((l) => (
                <button key={l} onClick={() => { set({ lang: l }); setLangOpen(false); }}
                  className="flex w-full justify-between border-0 bg-transparent px-2.5 py-2 text-[0.9375rem] text-ink cursor-pointer hover:bg-chip">
                  <span>{l === 'en' ? 'English' : '简体中文'}</span><span className="text-amber">{lang === l ? '●' : ''}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </header>
  );
}

function Strip() {
  const { t, lang } = useT();
  const now = useNow();
  const upDown = useUi((s) => s.upDown);
  const market = useUi((s) => s.market);
  const { data: sessions } = useSessions();
  const { data: indices } = useIndices();
  const live = useLive((s) => s.quotes);
  const flash = useLive((s) => s.flash);
  const connected = useLive((s) => s.connected);
  const tape = (indices || []).filter((q) => market === 'ALL' || q.mkt === market).map((q) => live[q.id] || q);
  return (
    <div className="flex-none h-[30px] flex items-center border-b border-line bg-strip overflow-hidden font-mono text-[0.8125rem]">
      {(sessions || []).map((s) => {
        const st = liveStatus(s, now);
        return (
          <div key={s.mkt} className="flex items-center gap-[7px] px-3 h-full border-r border-line flex-none"
            title={s.calendarSource.includes('unverified') ? t('calendar unverified') : s.calendarSource}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: STATUS_COLOR[st] }} />
            <span className="text-muted">{s.city}</span><span>{hm(now, s.tz)}</span>
            <span style={{ color: STATUS_COLOR[st] }}>{t(st)}</span>
          </div>
        );
      })}
      <div className="flex gap-[18px] px-3.5 overflow-hidden flex-1 min-w-0">
        {tape.map((q) => {
          const f = flash[q.id];
          const fresh = f && now - f.at < 1200;
          return (
            <span key={q.id} className="flex gap-1.5 flex-none px-1 py-[2px] rounded-[3px] transition-colors"
              style={{ background: fresh ? dirColor(f.dir, q.mkt, upDown, 0.25) : 'transparent' }}>
              <span className="text-dim">{lang === 'zh' ? q.nameZh || q.name : q.name}</span>
              <span>{q.price != null ? fmt(q.price) : '—'}</span>
              <span style={{ color: dirColor(Math.sign(q.pct || 0), q.mkt, upDown) }}>
                {q.pct != null ? (q.pct > 0 ? '+' : q.pct < 0 ? '−' : '') + Math.abs(q.pct).toFixed(2) + '%' : ''}
              </span>
            </span>
          );
        })}
      </div>
      <span className="flex-none px-3 border-l border-line h-full flex items-center gap-2 text-faint">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: connected ? 'var(--green)' : 'var(--red)' }} />
        {t(connected ? 'LIVE DATA' : 'STREAM OFFLINE')} · {t('PERSONAL USE · NOT ADVICE')}
      </span>
    </div>
  );
}

export function App() {
  const view = useUi((s) => s.view);
  const set = useUi((s) => s.set);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const m = /^F([1-5])$/.exec(e.key);
      if (m) {
        e.preventDefault();
        set({ view: VIEWS[+m[1] - 1][0] });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [set]);
  const lang = useUi((s) => s.lang);
  const theme = useUi((s) => s.theme);
  const textSize = useUi((s) => s.textSize);
  useEffect(() => {
    const el = document.documentElement;
    el.lang = lang === 'zh' ? 'zh-CN' : 'en';
    el.dataset.theme = theme;
    el.style.setProperty('--base-size', `${TEXT_PX[textSize]}px`);
  }, [lang, theme, textSize]);
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header />
      <Strip />
      <div className="flex-1 overflow-auto">
        {view === 'monitor' && <Monitor />}
        {view === 'market' && <Market />}
        {view === 'company' && <Company />}
        {view === 'industry' && <Industry />}
        {view === 'settings' && <Settings />}
      </div>
    </div>
  );
}
