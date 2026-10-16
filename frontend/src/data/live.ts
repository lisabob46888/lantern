// Live store: quotes, wire items and story updates kept current by the WebSocket stream.
import { create } from 'zustand';
import type { Quote, WireEvent } from '@/lib/types';

const WIRE_MAX = 400;

interface LiveState {
  connected: boolean;
  lastSeq: number;
  quotes: Record<string, Quote>;
  flash: Record<string, { dir: number; at: number }>;
  wire: WireEvent[];
  hidden: Set<string>;
  storyVersion: Record<string, number>;   // bumps when an AI read lands, so open panels refetch
  reportVersion: number;
  setConnected: (v: boolean) => void;
  setSeq: (s: number) => void;
  mergeQuotes: (q: Record<string, Quote>) => void;
  seedWire: (items: WireEvent[]) => void;
  upsertEvent: (e: WireEvent) => void;
  hideEvent: (id: string) => void;
  bumpStory: (id: string) => void;
  bumpReport: () => void;
}

export const useLive = create<LiveState>((set) => ({
  connected: false,
  lastSeq: 0,
  quotes: {},
  flash: {},
  wire: [],
  hidden: new Set(),
  storyVersion: {},
  reportVersion: 0,
  setConnected: (connected) => set({ connected }),
  setSeq: (lastSeq) => set((s) => (lastSeq > s.lastSeq ? { lastSeq } : s)),
  mergeQuotes: (q) =>
    set((s) => {
      const flash = { ...s.flash };
      const now = Date.now();
      for (const [id, v] of Object.entries(q)) {
        const old = s.quotes[id]?.price;
        if (old != null && v.price != null && v.price !== old) flash[id] = { dir: Math.sign(v.price - old), at: now };
      }
      return { quotes: { ...s.quotes, ...q }, flash };
    }),
  seedWire: (items) =>
    set((s) => {
      const byId = new Map(s.wire.map((e) => [e.id, e]));
      for (const e of items) byId.set(e.id, e);
      return { wire: [...byId.values()].sort((a, b) => b.ts - a.ts).slice(0, WIRE_MAX) };
    }),
  upsertEvent: (e) =>
    set((s) => {
      const rest = s.wire.filter((x) => x.id !== e.id);
      return { wire: [e, ...rest].sort((a, b) => b.ts - a.ts).slice(0, WIRE_MAX) };
    }),
  hideEvent: (id) =>
    set((s) => ({ wire: s.wire.filter((x) => x.id !== id), hidden: new Set(s.hidden).add(id) })),
  bumpStory: (id) => set((s) => ({ storyVersion: { ...s.storyVersion, [id]: (s.storyVersion[id] || 0) + 1 } })),
  bumpReport: () => set((s) => ({ reportVersion: s.reportVersion + 1 })),
}));
