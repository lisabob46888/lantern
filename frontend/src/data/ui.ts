// UI preferences and selections. Conveniences only are persisted (localStorage, guarded).
import { create } from 'zustand';
import type { MktFilter } from '@/lib/types';

export type View = 'monitor' | 'market' | 'company' | 'industry' | 'settings';
export type Lang = 'en' | 'zh';
export type UpDown = 'cn' | 'us' | 'market';
export type Theme = 'dark' | 'light';
export type TextSize = 's' | 'm' | 'l';
export const TEXT_PX: Record<TextSize, number> = { s: 15, m: 16, l: 18 };

const KEY = 'lantern-ui-v1';

function load(): Partial<UiState> {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}');
  } catch {
    return {};
  }
}

interface UiState {
  view: View;
  lang: Lang;
  market: MktFilter;
  upDown: UpDown;
  theme: Theme;
  textSize: TextSize;
  day: string | null;            // null = live session
  storyId: string | null;
  indexId: string | null;
  companyId: string | null;
  industryId: string | null;
  wireMode: 'all' | 'watch';
  set: (p: Partial<Omit<UiState, 'set'>>) => void;
}

const initialTheme: Theme = window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
const initialLang: Lang = /^zh/i.test(navigator.language || '') ? 'zh' : 'en';
const saved = load();

export const useUi = create<UiState>((set, get) => ({
  view: 'monitor',
  lang: initialLang,
  market: 'ALL',
  upDown: 'cn',
  theme: initialTheme,
  textSize: 'm',
  day: null,
  storyId: null,
  indexId: null,
  companyId: null,
  industryId: null,
  wireMode: 'all',
  ...saved,
  set: (p) => {
    set(p);
    const { view, lang, market, upDown, theme, textSize, indexId, companyId, industryId, wireMode } = { ...get(), ...p };
    try {
      localStorage.setItem(KEY, JSON.stringify({ view, lang, market, upDown, theme, textSize, indexId, companyId, industryId, wireMode }));
    } catch {
      /* storage unavailable: keep in memory only */
    }
  },
}));
