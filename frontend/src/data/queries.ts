// React Query hooks: one per snapshot the views read. Live deltas come from the stream store.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import { useLive } from './live';
import type { Bars, CalItem, NtkItem, Quote, Session, Status, Story, WireEvent } from '@/lib/types';

const enc = encodeURIComponent;
const g = <T,>(p: string) => () => api.get<T>(p);

export const useSessions = () =>
  useQuery({ queryKey: ['sessions'], queryFn: g<Session[]>('/sessions'), refetchInterval: 60_000 });

export const useStatus = () => useQuery({ queryKey: ['status'], queryFn: g<Status>('/status'), refetchInterval: 15_000 });

export const useIndices = () =>
  useQuery({ queryKey: ['indices'], queryFn: g<Quote[]>('/indices'), refetchInterval: 120_000 });

export const useQuotes = (ids: string[]) =>
  useQuery({
    queryKey: ['quotes', ids.join(',')],
    queryFn: () => api.get<Record<string, Quote>>(`/quotes?ids=${ids.map(enc).join(',')}`),
    enabled: ids.length > 0,
    refetchInterval: 60_000,
  });

export const useQuote = (id: string | null) =>
  useQuery({ queryKey: ['quote', id], queryFn: g<Quote>(`/securities/${enc(id || '')}/quote`), enabled: !!id });

export const useBars = (id: string | null, range: string) =>
  useQuery({
    queryKey: ['bars', id, range],
    queryFn: g<Bars>(`/securities/${enc(id || '')}/bars?range=${range}`),
    enabled: !!id,
    placeholderData: keepPreviousData,
    refetchInterval: range === '1D' ? 60_000 : false,
  });

export const useSecEvents = (id: string | null) =>
  useQuery({ queryKey: ['secEvents', id], queryFn: g<WireEvent[]>(`/securities/${enc(id || '')}/events`), enabled: !!id });

export const useWire = (market: string, date: string | null) =>
  useQuery({
    queryKey: ['wire', market, date],
    queryFn: g<{ items: WireEvent[]; aiEnabled: boolean }>(`/wire?market=${market}${date ? `&date=${date}` : ''}`),
  });

export const useArchiveDays = () =>
  useQuery({ queryKey: ['archiveDays'], queryFn: g<{ date: string; events: number }[]>('/archive/days'), refetchInterval: 300_000 });

export const useStory = (id: string | null) => {
  const v = useLive((s) => (id ? s.storyVersion[id] || 0 : 0));
  return useQuery({
    queryKey: ['story', id, v],
    queryFn: g<Story>(`/stories/${enc(id || '')}`),
    enabled: !!id,
    placeholderData: keepPreviousData,
  });
};

export const useNtk = (market: string, date: string | null) =>
  useQuery({
    queryKey: ['ntk', market, date],
    queryFn: g<{ date: string; items: NtkItem[]; aiEnabled: boolean }>(`/need-to-know?market=${market}${date ? `&date=${date}` : ''}`),
    refetchInterval: 60_000,
  });

export const useCalendar = (market: string) =>
  useQuery({ queryKey: ['calendar', market], queryFn: g<CalItem[]>(`/calendar?market=${market}&limit=12`), refetchInterval: 600_000 });

export const usePostMarket = (market: string, date: string | null) => {
  const v = useLive((s) => s.reportVersion);
  return useQuery({
    queryKey: ['pm', market, date, v],
    queryFn: g<Record<string, unknown>>(`/reports/post-market?market=${market}${date ? `&date=${date}` : ''}`),
    retry: false,
  });
};

export const useLists = () =>
  useQuery({ queryKey: ['lists'], queryFn: g<{ ix: string[]; co: string[]; ind: string[] }>('/watchlists') });

export function usePutList() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, items }: { name: string; items: string[] }) => api.putList(name, items),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lists'] }),
  });
}

export const useCompany = <T,>(id: string | null, part: string, enabled = true) =>
  useQuery({
    queryKey: ['company', id, part],
    queryFn: g<T>(`/companies/${enc(id || '')}/${part}`),
    enabled: !!id && enabled,
    staleTime: 300_000,
  });

export const useIndustries = () =>
  useQuery({ queryKey: ['industries'], queryFn: g<{ id: string; name: string; nameZh: string; events7d: number }[]>('/industries') });

export const useIndustry = <T,>(id: string | null, market: string) => {
  const v = useLive((s) => s.reportVersion);   // bumped when a research pack lands
  return useQuery({ queryKey: ['industry', id, market, v], queryFn: g<T>(`/industries/${id}?market=${market}`), enabled: !!id, staleTime: 300_000, placeholderData: keepPreviousData });
};

export const useSearch = (q: string) =>
  useQuery({ queryKey: ['search', q], queryFn: g<Quote[]>(`/securities/search?q=${enc(q)}`), enabled: q.trim().length > 0, staleTime: 60_000 });
