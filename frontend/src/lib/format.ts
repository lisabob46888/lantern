import type { Mkt } from './types';
import type { UpDown } from '@/data/ui';

export const fmt = (n: number | null | undefined, d = 2) =>
  n == null || Number.isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

export const pct = (n: number | null | undefined, d = 2) =>
  n == null || Number.isNaN(n) ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(d) + '%';

export function big(n: number | null | undefined, ccy = '') {
  if (n == null || Number.isNaN(n)) return '—';
  const a = Math.abs(n);
  const s = a >= 1e12 ? (n / 1e12).toFixed(2) + 'T' : a >= 1e9 ? (n / 1e9).toFixed(1) + 'B' : a >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : fmt(n, 0);
  return ccy + s;
}

export const priceDigits = (v: number | null | undefined) => (v != null && Math.abs(v) >= 1000 ? 2 : v != null && Math.abs(v) < 10 ? 3 : 2);

const GREEN = 'var(--green)';
const RED = 'var(--red)';
const FLAT = 'rgb(var(--muted))';

/** Up/down colour. 'cn' = red up (A-share convention), 'us' = green up, 'market' = per market. */
export function dirColor(dir: number, mkt: Mkt | undefined, conv: UpDown, alpha?: number): string {
  if (!dir) return FLAT;
  const redUp = conv === 'cn' || (conv === 'market' && (mkt === 'CN' || mkt === 'HK'));
  const c = (dir > 0) === redUp ? RED : GREEN;
  return alpha == null ? c : `color-mix(in oklch, ${c} ${Math.round(alpha * 100)}%, transparent)`;
}

export const hm = (ms: number, tz?: string) =>
  new Date(ms).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz });

export const dayShort = (iso: string, lang: string) =>
  new Date(iso + 'T12:00:00Z').toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

export const dateTime = (ms: number, lang: string) =>
  new Date(ms).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });

export function countdown(ms: number, now: number): string {
  let s = Math.max(0, Math.floor((ms - now) / 1000));
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  return `${m}m ${String(s % 60).padStart(2, '0')}s`;
}

export const MKT_LABEL: Record<Mkt, string> = { US: 'US', CN: 'China A', HK: 'Hong Kong' };
