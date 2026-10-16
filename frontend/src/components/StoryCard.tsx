// "AI READ" card used beside event lists on the Index and Company pages (prototype layout):
// title, date / IMPACT / DIRECTION, one-line gist, detail, bull and bear, confidence, Open AI read →.
import { useStory } from '@/data/queries';
import { useUi } from '@/data/ui';
import { useT } from '@/i18n';
import { dateTime, dirColor } from '@/lib/format';
import { eventTitle } from './AIRead';
import { Badge } from './page';
import type { Mkt } from '@/lib/types';

export function StoryCard({ storyId, label, dir, mkt }: { storyId: string | null; label?: string; dir?: number; mkt?: Mkt }) {
  const { t, bi, lang } = useT();
  const upDown = useUi((s) => s.upDown);
  const set = useUi((s) => s.set);
  const { data: st } = useStory(storyId);
  if (!storyId) return <div className="text-[0.9375rem] text-faint">{t('Select a news item or catalyst to see the AI read.')}</div>;
  if (!st) return <div className="text-[0.9375rem] text-faint animate-pulse">{t('Loading…')}</div>;
  const lead = st.events.find((e) => e.state === 'done') || st.events[0];
  const r = st.read;
  const d = dir ?? (st.sentiment === 'bullish' ? 1 : st.sentiment === 'bearish' ? -1 : 0);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-between items-center">
        <span className="text-[0.75rem] font-semibold tracking-[.08em] uppercase text-sky">{t('AI read')}</span>
        {label && <Badge label={label} dir={d} mkt={mkt} />}
      </div>
      <div className="text-[1.25rem] font-medium leading-[1.3]">{lead ? eventTitle(lead, bi) : st.headline}</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.75rem] text-dim pb-3 border-b border-line">
        <span>{dateTime(lead?.ts || st.lastSeen, lang)}</span>
        {st.impact != null && <span>{t('IMPACT')} <span className="text-ink">{st.impact}/10</span></span>}
        <span>{t('DIRECTION')} <span style={{ color: dirColor(d, mkt, upDown) }}>{d > 0 ? t('▲ Positive') : d < 0 ? t('▼ Negative') : t('— Mixed')}</span></span>
      </div>
      {lead?.ai?.comment && <p className="m-0 text-[1rem] leading-[1.55]">{bi(lead.ai.comment)}</p>}
      {r ? <p className="m-0 text-[0.9375rem] leading-[1.6] text-muted">{bi(r.detail) || bi(r.simple)}</p>
        : st.readState === 'pending' ? <div className="text-[0.875rem] text-faint animate-pulse">{t('Generating the AI read…')}</div>
          : st.readState === 'disabled' ? <div className="text-[0.875rem] text-faint">{t('AI reads are off: add GLM_API_KEY to .env')}</div> : null}
      {r && (
        <>
          <div className="border-t border-line pt-3">
            <div className="text-[0.75rem] font-semibold tracking-[.08em] uppercase" style={{ color: dirColor(1, mkt, upDown) }}>{t('Bull case')}</div>
            <p className="m-0 mt-1 text-[0.9375rem] leading-[1.55] text-muted">{bi(r.bull)}</p>
          </div>
          <div className="border-t border-line pt-3">
            <div className="text-[0.75rem] font-semibold tracking-[.08em] uppercase" style={{ color: dirColor(-1, mkt, upDown) }}>{t('Bear case')}</div>
            <p className="m-0 mt-1 text-[0.9375rem] leading-[1.55] text-muted">{bi(r.bear)}</p>
          </div>
          <div className="border-t border-line pt-3 font-mono text-[0.75rem] text-dim">
            {t('Confidence')} <span className="text-ink">{r.confidence ?? '—'}%</span> &nbsp; {bi(r.horizon)}
          </div>
        </>
      )}
      <button onClick={() => set({ view: 'monitor', storyId })}
        className="self-start border border-amber bg-transparent text-amber font-mono text-[0.75rem] px-2.5 py-1 rounded-[2px] cursor-pointer">
        {t('Open AI read →')}
      </button>
    </div>
  );
}
