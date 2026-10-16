// English strings are the keys; zh.json holds the prototype's UI dictionary plus zh.extra.json.
import zh from './zh.json';
import { useUi } from '@/data/ui';
import type { Bi } from '@/lib/types';

const ZH = zh as Record<string, string>;
const lower: Record<string, string> = Object.fromEntries(Object.entries(ZH).map(([k, v]) => [k.toLowerCase(), v]));

export function translate(en: string, lang: string): string {
  if (lang !== 'zh') return en;
  return ZH[en] ?? lower[en.toLowerCase()] ?? en;
}

/** Hook returning t(en) and bi({en, zh}) bound to the current language. */
export function useT() {
  const lang = useUi((s) => s.lang);
  const t = (en: string) => translate(en, lang);
  const bi = (b: Bi | null | undefined, fallback = '') => {
    if (!b) return fallback;
    return (lang === 'zh' ? b.zh || b.en : b.en || b.zh) || fallback;
  };
  return { t, bi, lang };
}
