// Typed REST client for /api/v1. Same origin in production; Vite proxies /api in dev.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!r.ok) {
    let msg = r.statusText;
    try {
      msg = (await r.json()).detail || msg;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  get: <T>(path: string) => req<T>(path),
  status: () => req('/status'),
  sessions: () => req('/sessions'),
  indices: (market = 'ALL') => req(`/indices?market=${market}`),
  quotes: (ids: string[]) => req(`/quotes?ids=${ids.map(enc).join(',')}`),
  search: (q: string) => req(`/securities/search?q=${enc(q)}`),
  quote: (id: string) => req(`/securities/${enc(id)}/quote`),
  bars: (id: string, range: string) => req(`/securities/${enc(id)}/bars?range=${range}`),
  secEvents: (id: string) => req(`/securities/${enc(id)}/events`),
  wire: (market: string, date?: string) => req(`/wire?market=${market}${date ? `&date=${date}` : ''}`),
  archiveDays: () => req('/archive/days'),
  story: (id: string) => req(`/stories/${enc(id)}`),
  ntk: (market: string, date?: string) => req(`/need-to-know?market=${market}${date ? `&date=${date}` : ''}`),
  calendar: (market = 'ALL') => req(`/calendar?market=${market}&limit=12`),
  postMarket: (market: string, date?: string) => req(`/reports/post-market?market=${market}${date ? `&date=${date}` : ''}`),
  lists: () => req('/watchlists'),
  putList: (name: string, items: string[]) => req(`/watchlists/${name}`, { method: 'PUT', body: JSON.stringify(items) }),
  company: (id: string, part: string) => req(`/companies/${enc(id)}/${part}`),
  industries: () => req('/industries'),
  industry: (id: string, market: string) => req(`/industries/${id}?market=${market}`),
};
