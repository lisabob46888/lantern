// Shapes returned by the Lantern backend (/api/v1).

export type Mkt = 'US' | 'CN' | 'HK';
export type MktFilter = Mkt | 'ALL';
export type Bi = { en: string; zh: string };

export interface Meta {
  source: string | null;
  tier: string | null;
  fetchedAt: number;
}

export interface SecRef {
  id: string;
  mkt: Mkt;
  code: string;
  ticker: string;
  kind: 'stock' | 'index';
  name: string;
  nameZh: string;
  ccy: string;
}

export interface Quote extends SecRef {
  price: number | null;
  prevClose?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  chg?: number | null;
  pct?: number | null;
  volume?: number | null;
  time?: string;
  source?: string;
  peTtm?: number;
  pb?: number;
  eps?: number;
  mcap?: number;
  hi52?: number;
  lo52?: number;
  turnoverPct?: number;
}

export interface Bar { t: string; o: number; h: number; l: number; c: number; v: number }
export interface Bars extends Meta { id: string; range: string; unit: 'i' | 'd' | 'w' | 'm'; bars: Bar[] }

export interface WireEvent {
  id: string;
  storyId: string | null;
  kind: 'news' | 'filing' | 'rss' | 'announcement' | 'macro';
  source: string;
  url: string | null;
  ts: number;
  receivedAt: number;
  mkts: Mkt[];
  symbols: string[];
  industries: string[];
  title: string;
  body: string;
  lang: string | null;
  impact: number | null;
  ai: { title: Bi; comment: Bi; sentiment?: string; dirs?: Record<string, number>; model?: string } | null;
  state: 'pending' | 'done' | 'skipped' | 'failed';
}

export interface DeepRead {
  simple: Bi; detail: Bi; horizon: Bi; bull: Bi; bear: Bi;
  affected: { id: string; dir: number; note: Bi }[];
  ripple: { where: Bi; text: Bi }[];
  analog: { title: Bi; text: Bi } | null;
  confidence: number | null;
  sources: { title: string; url: string | null; source: string }[];
}

export interface Story {
  id: string;
  headline: string;
  firstSeen: number;
  lastSeen: number;
  impact: number | null;
  sentiment: string | null;
  mkts: Mkt[];
  symbols: string[];
  events: WireEvent[];
  readState: 'ready' | 'pending' | 'disabled';
  read: DeepRead | null;
  readMeta: { model: string; promptVersion: string; at: number } | null;
  quotes: Record<string, Quote>;
}

export interface Session {
  mkt: Mkt;
  city: string;
  tz: string;
  sessions: [number, number][];
  status: 'OPEN' | 'PRE' | 'LUNCH' | 'POST' | 'CLOSED';
  localDate: string;
  tradingDays: string[];
  lastCompleted: string | null;
  calendarSource: string;
}

export interface CalItem {
  id: string; kind: string; mkt: Mkt; title: string; titleZh?: string | null; at: number;
  source: string; url?: string | null; symbol?: string | null;
}

export interface NtkItem { storyId: string; impact: number; mkts: Mkt[]; title: Bi; why: Bi; ts: number }

export interface Status {
  llm: { enabled: boolean; model: string };
  keys: { glm: boolean; finnhub: boolean; tushare: boolean; secContact: boolean };
  pollers: Record<string, { lastRun?: number; lastOk?: number; lastError?: string; lastErrorAt?: number; items?: number }>;
  breakers: Record<string, { fails: number; openFor: number }>;
  sources: { source: string; ok_count: number; fail_count: number; last_ok: number | null; last_error: string | null; last_error_at: number | null }[];
  personalUseOnly: boolean;
}
