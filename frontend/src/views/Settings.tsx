import { useStatus } from '@/data/queries';
import { useUi } from '@/data/ui';
import { useT } from '@/i18n';
import { dateTime } from '@/lib/format';
import { Label, Loading, Panel, Tabs } from '@/components/ui';

export function Settings() {
  const { t, lang } = useT();
  const { upDown, theme, textSize, set } = useUi();
  const { data: st, isLoading } = useStatus();
  return (
    <div className="flex flex-col gap-px bg-line min-h-full">
      <div className="flex flex-wrap gap-px">
        <Panel className="flex-[1_1_360px]" title={t('Settings')} bodyClass="p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5"><Label>{t('Language')}</Label>
            <Tabs items={[{ id: 'en', label: 'English' }, { id: 'zh', label: '简体中文' }]} value={lang} onChange={(v) => set({ lang: v })} /></div>
          <div className="flex flex-col gap-1.5"><Label>{t('Theme')}</Label>
            <Tabs items={[{ id: 'dark', label: t('Dark mode') }, { id: 'light', label: t('Light mode') }]} value={theme} onChange={(v) => set({ theme: v })} /></div>
          <div className="flex flex-col gap-1.5"><Label>{t('Text size')}</Label>
            <Tabs items={[{ id: 's', label: t('Small') }, { id: 'm', label: t('Medium') }, { id: 'l', label: t('Large') }]} value={textSize} onChange={(v) => set({ textSize: v })} /></div>
          <div className="flex flex-col gap-1.5"><Label>{t('Up/down colours')}</Label>
            <Tabs items={[{ id: 'cn', label: t('Red up (A-share)') }, { id: 'us', label: t('Green up (US)') }, { id: 'market', label: t('By market') }]} value={upDown} onChange={(v) => set({ upDown: v })} /></div>
          <div className="flex flex-col gap-1.5"><Label>{t('API keys')}</Label>
            {isLoading && <Loading />}
            {st && Object.entries({ 'GLM-5.3 (AI reads)': st.keys.glm, Finnhub: st.keys.finnhub, 'Tushare Pro': st.keys.tushare, 'SEC EDGAR contact': st.keys.secContact }).map(([k, v]) => (
              <div key={k} className="flex justify-between text-[0.9375rem] border-b border-line2 py-1"><span>{k}</span><span className={`font-mono text-[0.8125rem] ${v ? 'text-[color:var(--green)]' : 'text-amber'}`}>{t(v ? 'configured' : 'missing')}</span></div>
            ))}
            <span className="text-[0.8125rem] text-faint">.env: GLM_API_KEY · FINNHUB_KEY · TUSHARE_TOKEN · SEC_CONTACT</span>
          </div>
          <p className="m-0 text-[0.875rem] text-faint leading-[1.5]">{t('Personal use only. Data from site front-end APIs is for private research and must not be redistributed.')}</p>
        </Panel>
        <Panel className="flex-[1_1_520px]" title={t('Data sources')} bodyClass="p-4 flex flex-col gap-4">
          {st && (
            <>
              <div><Label>{t('Pollers')}</Label>
                {Object.entries(st.pollers).map(([k, p]) => (
                  <div key={k} className="grid grid-cols-[130px_150px_60px_minmax(0,1fr)] gap-2 text-[0.875rem] border-b border-line2 py-1 font-mono">
                    <span>{k}</span><span className="text-faint">{p.lastOk ? dateTime(p.lastOk, lang) : '—'}</span><span>{p.items ?? 0}</span><span className="text-amber truncate" title={p.lastError}>{p.lastError && (p.lastErrorAt ?? 0) > (p.lastOk ?? 0) ? p.lastError : ''}</span>
                  </div>
                ))}
              </div>
              <div><Label>{t('Sources')}</Label>
                {st.sources.map((s) => {
                  const br = st.breakers[s.source];
                  return (
                    <div key={s.source} className="grid grid-cols-[170px_60px_60px_minmax(0,1fr)] gap-2 text-[0.875rem] border-b border-line2 py-1 font-mono">
                      <span>{s.source}</span><span className="text-[color:var(--green)]">{s.ok_count}</span><span className="text-amber">{s.fail_count}</span>
                      <span className="text-faint truncate" title={s.last_error || ''}>{br?.openFor ? `circuit open ${br.openFor}s · ` : ''}{s.last_error || ''}</span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
